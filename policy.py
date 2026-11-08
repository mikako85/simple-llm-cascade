"""Security policies, execution modes, and tool interception logic.

This module defines the agent's operation modes (SANDBOX, YOLO, ASK),
verifies command safety (e.g. blocking privilege escalation), renders file diffs,
and prompts the user for confirmation when mutating actions are requested.
"""

import difflib
import re
import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from prompt_toolkit import prompt
from env_utils import is_firejail_available


class ExecutionMode(str, Enum):
    """Execution modes governing agent autonomy and isolation."""

    SANDBOX = 'sandbox'  # Isolated bash inside a Firejail sandbox (read-only root, no network access)
    YOLO = 'yolo'        # Full autonomous host execution without confirmation
    ASK = 'ask'          # Host execution with interactive user confirmation


    @classmethod
    def from_string(cls, value: str | None, default: 'ExecutionMode' = ASK) -> 'ExecutionMode':
        """Parse string to ExecutionMode safely, falling back to default."""
        if not value:
            return default
        try:
            return cls(value.strip().lower())
        except ValueError:
            return default


@dataclass(frozen=True)
class InterceptResult:
    """Outcome of a tool call interception.

    Attributes:
        allowed: True if the tool execution is permitted, False if blocked/rejected.
        rejection_reason: Explanation for rejection sent back to the LLM.
    """

    allowed: bool
    rejection_reason: str = ''

FORBIDDEN_ROOT_COMMANDS = {'sudo', 'pkexec', 'doas'}

INSPECTED_INTERPRETERS = {'sh', 'bash', 'zsh', 'dash', 'ksh', 'python', 'python3', 'perl', 'ruby'}

COMMAND_WRAPPERS = {
    'env', 'time', 'nohup', 'exec', 'xargs', 'command',
    'builtin', 'nice', 'timeout', 'strace', 'ltrace', 'eval'
}

COMMAND_DELIMITERS = {';', '&&', '||', '|', '&', '\n', '`', '$(', '(', ')', '{', '}'}

SENSITIVE_PATH_PATTERNS = [
    r'~/\.simple-llm-cascade',
    r'/\.simple-llm-cascade',
    r'~/\.ssh',
    r'~/\.aws',
    r'~/\.gnupg',
    r'/etc/shadow',
    r'/etc/sudoers',
    r'(?:^|[\s/])\.env(?:\.[\w-]+)?(?:\s|$)',
]


def check_privilege_escalation(command: str, depth: int = 0) -> tuple[bool, str]:
    """Inspect bash command line for privilege escalation and secret exfiltration."""
    if not command or not command.strip():
        return False, ''

    if depth > 5:
        return True, 'Security violation: Command nesting depth exceeded limit.'

    # 1. Block direct access to secret files from bash
    for pattern in SENSITIVE_PATH_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return (
                True,
                'Security policy violation: Direct command-line access to sensitive credentials or environment files is strictly forbidden.'
            )

    # 2. Block piping into a shell interpreter (echo ... | sh, base64 | bash)
    if re.search(r'\|\s*(?:ba|da|z)?sh\b', command):
        return (
            True,
            'Security policy violation: Piping dynamic output directly into a shell interpreter is strictly prohibited.'
        )

    # 3. Fast check for forbidden binaries
    raw_forbidden_check = re.search(r'(?:^|[;&|`\n\(\)\{]|\$\()\s*(sudo|doas|pkexec|su)(?:\s+|$)', command)
    if raw_forbidden_check:
        forbidden_bin = raw_forbidden_check.group(1)
        reason = f'Privilege escalation ("{forbidden_bin}")' if forbidden_bin != 'su' else 'Switching users ("su")'
        return True, f'Security policy violation: {reason} is strictly forbidden.'

    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ''
        tokens = list(lexer)
    except Exception:
        return True, 'Security policy violation: Malformed command string or unclosed quotes.'

    idx = 0
    num_tokens = len(tokens)

    while idx < num_tokens:
        token = tokens[idx]

        if token in COMMAND_DELIMITERS or any(sep in token for sep in (';', '&&', '||', '|', '(', ')', '{', '}')):
            idx += 1
            continue

        if '=' in token and not token.startswith('='):
            idx += 1
            continue

        cmd_name = token.strip().split('/')[-1]

        # Block dynamic command substitution where the binary name is expected: $(echo sudo) id
        if cmd_name.startswith('$(') or cmd_name.startswith('`'):
            return True, 'Security policy violation: Dynamic command substitution in executable position is prohibited.'

        if cmd_name in FORBIDDEN_ROOT_COMMANDS:
            return True, f'Security policy violation: Privilege escalation ("{cmd_name}") is strictly forbidden.'
        if cmd_name == 'su':
            return True, 'Security policy violation: Switching user accounts ("su") is strictly forbidden.'

        # Wrapper handling: skip flags and wrapper-specific arguments (timeouts, nice levels)
        if cmd_name in COMMAND_WRAPPERS:
            idx += 1
            # eval: collects the remaining tokens and runs them recursively as a shell command
            if cmd_name == 'eval':
                eval_payload = ' '.join(tokens[idx:])
                return check_privilege_escalation(eval_payload, depth + 1)

            while idx < num_tokens:
                sub_token = tokens[idx]
                # Skip flags (-i, -n, -v, etc.) and variable assignments (VAR=val)
                if sub_token.startswith('-') or ('=' in sub_token and not sub_token.startswith('=')):
                    idx += 1
                    continue
                # For timeout, skip the duration argument (e.g. 5, 10s, 1m)
                if cmd_name == 'timeout' and re.match(r'^\d+(\.\d+)?[smhd]?$', sub_token):
                    idx += 1
                    continue
                # For nice, skip the numeric priority
                if cmd_name == 'nice' and re.match(r'^-?\d+$', sub_token):
                    idx += 1
                    continue
                break
            continue

        # Inspect find ... -exec cmd \;
        if cmd_name == 'find':
            exec_indices = [i for i, t in enumerate(tokens[idx:], start=idx) if t in ('-exec', '-execdir')]
            for e_idx in exec_indices:
                if e_idx + 1 < num_tokens:
                    sub_cmd_tokens = []
                    for t in tokens[e_idx + 1:]:
                        if t in (';', '\\;', '+'):
                            break
                        sub_cmd_tokens.append(t)
                    sub_res, sub_reason = check_privilege_escalation(' '.join(sub_cmd_tokens), depth + 1)
                    if sub_res:
                        return True, sub_reason
            idx += 1
            continue

        # Interpreters (python, bash, sh, perl...) invoked with the -c flag
        if cmd_name in INSPECTED_INTERPRETERS or cmd_name.startswith('python'):
            idx += 1
            while idx < num_tokens and tokens[idx] not in COMMAND_DELIMITERS:
                arg = tokens[idx]
                if arg in ('-c', '-ic'):
                    if idx + 1 < num_tokens:
                        sub_cmd = tokens[idx + 1]
                        # Inline scan of the script payload for sudo/su invocations
                        if re.search(r'\b(sudo|pkexec|doas)\b', sub_cmd):
                            return True, 'Security policy violation: Privilege escalation inside interpreter payload is forbidden.'
                        if re.search(r'\bsu\b', sub_cmd):
                            return True, 'Security policy violation: User switching ("su") inside interpreter payload is forbidden.'
                        # Recurse into the payload
                        sub_res, sub_reason = check_privilege_escalation(sub_cmd, depth + 1)
                        if sub_res:
                            return True, sub_reason
                idx += 1
            continue

        idx += 1
        while idx < num_tokens and tokens[idx] not in COMMAND_DELIMITERS:
            if '$(' in tokens[idx] or '`' in tokens[idx]:
                subshell_match = re.search(r'\$\((.*?)\)|`(.*?)`', tokens[idx])
                if subshell_match:
                    sub_payload = subshell_match.group(1) or subshell_match.group(2)
                    sub_res, sub_reason = check_privilege_escalation(sub_payload, depth + 1)
                    if sub_res:
                        return True, sub_reason
            idx += 1

    return False, ''

def format_file_diff(file_path: str, new_content: str, max_diff_lines: int = 40) -> str:
    """Generate a colorized unified diff for terminal display."""
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()

    # Case 1: Brand new file
    if not path.exists():
        lines = new_content.splitlines()
        preview = lines[:8]
        preview_text = "\n".join(f"  \033[32m+ {line}\033[0m" for line in preview)
        more = f"\n  \033[33m... ({len(lines) - 8} more lines)\033[0m" if len(lines) > 8 else ""
        return (
            f"  \033[1;32m[NEW FILE]\033[0m '{file_path}' ({len(lines)} lines, {len(new_content)} bytes)\n"
            f"{preview_text}{more}"
        )

    # Case 2: Overwrite existing file -> Unified diff
    try:
        old_content = path.read_text(encoding='utf-8', errors='replace')
    except Exception as e: 
        return f"  \033[1;33m[OVERWRITE FILE]\033[0m '{file_path}' (Unable to read original: {e})"

    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = list(difflib.unified(
        old_lines,
        new_lines,
        fromfile=f'a/{file_path}',
        tofile=f'b/{file_path}',
        n=3
    ))

    if not diff:
        return f"  \033[33m[NO CHANGES]\033[0m File '{file_path}' content is identical."

    formatted = []
    truncated = len(diff) > max_diff_lines
    diff_slice = diff[:max_diff_lines] if truncated else diff

    for line in diff_slice:
        line_clean = line.rstrip('\n')
        if line.startswith('+++') or line.startswith('---'):
            formatted.append(f"  \033[1m{line_clean}\033[0m")
        elif line.startswith("@@"):
            formatted.append(f"  \033[36m{line_clean}\033[0m")
        elif line.startswith("+"):
            formatted.append(f"  \033[32m{line_clean}\033[0m")
        elif line.startswith("-"):
            formatted.append(f"  \033[31m{line_clean}\033[0m")
        else:
            formatted.append(f"  {line_clean}")

    if truncated:
        formatted.append(f"  \033[33m... [diff truncated, total {len(diff)} lines]\033[0m")

    return "\n".join(formatted)


def prompt_user_for_confirmation(prompt_text: str = 'Apply this action? [y/N]') -> bool:
    """Prompt the user for interactive confirmation in the terminal."""
    try:
        answer = input(prompt_text).strip().lower()
        return answer in ('y', 'yes')
    except (EOFError, KeyboardInterrupt):
        print()
        return False


class ToolInterceptor:
    """Gateway that intercepts tool execution based on the active ExecutionMode."""
    def __init__(self, default_mode: ExecutionMode = ExecutionMode.ASK):
        self.mode = default_mode


    def set_mode(self, mode: ExecutionMode):
        """Update the active execution mode."""
        self.mode = mode


    def intercept(
        self,
        tool_name: str,
        tool_args: dict,
        current_mode: ExecutionMode | None = None,
    ) -> InterceptResult:
        """Evaluate whether a tool call should proceed
        
        Args:
            tool_name: Name of the tool to be executed.
            tool_args: Arguments passed by the language model.
            current_mode: Mode override, or active instance mode if None.

        Returns:
            InterceptResult indicating whether execution can proceed.
        """
        mode = current_mode or self.mode

        # Universal Security Filter (Applies in ALL modes, including YOLO)
        if tool_name == 'run_bash_command':
            cmd = tool_args.get('command', '')
            is_forbidden, reason = check_privilege_escalation(cmd)
            if is_forbidden:
                return InterceptResult(allowed=False, rejection_reason=reason)

        # YOLO Mode Handling (No interactive confirmation)
        if mode == ExecutionMode.YOLO:
            return InterceptResult(allowed=True)

        
        # SANDBOX Mode -> Verify sandbox availability
        if mode == ExecutionMode.SANDBOX:
            if not is_firejail_available():
                return InterceptResult(
                    allowed=False,
                    rejection_reason=(
                        "Sandbox mode is enabled, but firejail is not available.\n"
                        "Switch execution mode to 'ask' or 'yolo'."
                    ),
                )
            return InterceptResult(allowed=True)

        # ASK Mode -> Interactive confirmation for mutating operations
        if mode == ExecutionMode.ASK:
            if tool_name == 'write_file':
                path = tool_args.get('path', '')
                content = tool_args.get('content', '')

                print(f"\n\033[1;34m[ASK MODE]\033[0m Agent wants to write file: \033[1m{path}\033[0m")
                print(format_file_diff(path, content))

                if not prompt_user_for_confirmation('\033[1mSave changes to this file? [y/N]: \033[0m'):
                    return InterceptResult(
                        allowed=False,
                        rejection_reason=(
                            f'Action cancelled by user: writing to "{path}" was rejected. '
                            'Please propose an alternative approach or ask for clarification.'
                        ),
                    )
                return InterceptResult(allowed=True)

            elif tool_name == 'run_bash_command':
                cmd = tool_args.get('command', '')

                print(f"\n\033[1;34m[ASK MODE]\033[0m Agent wants to execute command:")
                print(f"  \033[1;33m$\033[0m \033[1m{cmd}\033[0m")

                if not prompt_user_for_confirmation('\033[1mExecute this command? [y/N]: \033[0m'):
                    return InterceptResult(
                        allowed=False,
                        rejection_reason=(
                            f'Action cancelled by user: command "{cmd}" was rejected. '
                            'Please propose an alternative approach or ask for clarification.'
                        ),
                    )
                return InterceptResult(allowed=True)
                
            # Read-only operations (read_text_document, list_directory) are always allowed
        return InterceptResult(allowed=True)
