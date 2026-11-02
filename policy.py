"""Security policies, execution modes, and tool interception logic.

This module defines the agent's operation modes (SANDBOX, YOLO, ASK),
verifies command safety(e.g. blocking privilege escalation) and prepares
the interception gateway before tools are executed.
"""

import re
import shlex
from dataclasses import dataclass
from enum import Enum


class ExecutionMode(str, Enum):
    """Execution modes governing agent autonomy and isolation."""

    SANDBOX = 'sandbox' # Isolated bash inside a Firejail sandbox(read-only root, no network access)
    YOLO = 'yolo'       # Full autonomous host execution without confirmation
    ASK = 'ask'         # Host execution with interactive user confirmation


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
    """Outcome of tool call interception

    Attributes:
        allowed:True if the tool execution is permitted, False if blocked/rejected.
        rejection_reason: Explanation for rejection sent back to the LLM.
    """

    allowed: bool
    rejection_reason: str

#Commands that elevate privileges or switch users
FORBIDDEN_ROOT_COMMANDS = {'sudo', 'pkexec', 'doas'}

#Command wrappers that execute the subsequent argument as command
COMMAND_WRAPPERS = {'env', 'time', 'nohup', 'exec', 'xargs'}

COMMAND_DELIMITERS = {';', '&&', '||', '|', '&', '\n', '`', '$(', '(', ')'}

def check_privilege_escalation(command: str) -> tuple[bool, str]:
    """Inspect a bash command line for privilege escalation attempts.

    Correctly handles command chains (&&, ||, ;, |), wrappers (env, nohup),
    env vars (VAR=val sudo), absolute paths (/usr/bin/sudo), while ignoring
    arguments and commit messages.

    Args:
        command: Raw bash command string.

    Returns:
        tuple[bool, str]: (is_forbidden, rejection_reason)
    """
    if not command or not command.strip():
        return False, ''

    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ''
        tokens = list(lexer)
        is_cmd_start = True

        for token in tokens:
            if is_cmd_start:
                # 1. Skip environment variable assignments (e.g. VAR=val sudo ...)
                if '=' in token and not token.startswith('='):
                    continue

                # 2. Extract base executable name (handles /usr/bin/sudo -> sudo)
                cmd_name = token.strip().split('/')[-1]

                # 3. Check for privilege escalation binaries
                if cmd_name in FORBIDDEN_ROOT_COMMANDS:
                    return (
                        True,
                        f'Security policy violation: Privilege escalation ("{cmd_name}") is strictly forbidden.'
                    )
                if cmd_name == 'su':
                    return (
                        True,
                        'Security policy violation: Switching user accounts ("su") is strictly forbidden.'
                    )

                # 4. If it's a wrapper like 'env' or 'nohup', the next token is still a command
                if cmd_name in COMMAND_WRAPPERS:
                    continue

                # Normal command recognized (e.g. echo, git, npm) -> next tokens are arguments
                is_cmd_start = False

            elif token in COMMAND_DELIMITERS or any(sep in token for sep in (';', '&&', '||', '|')):
                is_cmd_start = True

    except Exception:
        # Fallback to regex pattern supporting env assignments: VAR=val sudo ...
        pattern = r'(?:^|[;&|`\n]\s*|&&|\|\|)(?:\s*[\w]+=\S+)*\s*(?:[/\w.-]+/)?(sudo|doas|pkexec|su)(?:\s+|$)'
        match = re.search(pattern, command)
        if match:
            forbidden_bin = match.group(1)
            return (
                True,
                f'Security policy violation: Privilege escalation ("{forbidden_bin}") is strictly forbidden.'
            )

    return False, ''


class ToolInterceptor:
    """Gateway that interxepts tool execution based on the active ExecurionMode."""
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
        """Evaluate whether a tool call should be proceed
        
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

        # Base Mode Handling (Detailed interactive confirmation for each mode)
        return InterceptResult(allowed=True)
