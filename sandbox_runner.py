"""Execution of shell commands with or without Firejail sandbox isolation.

This module provides two execution runners:
1. SandboxRunner: Runs commands inside an isolated firejail jail (native Linux only).
2. HostRunner: Runs commands directly on the host (for WSK, ASK, and YOLO modes)
   with process group isolation, timeout enforcement, and output truncation.
"""

import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    """Outcome of an executed command.

    Attributes:
        returncode: Exit code of the command (or -1 when the runner fails).
        stdout: Captured standard output, possibly truncated.
        stderr: Captured standard error.
        truncated: True when stdout exceeded the configured limit.
    """

    returncode: int
    stdout: str
    stderr: str
    truncated: bool


def get_sanitized_env() -> dict[str, str]:
    """Return a clean environment dict stripped of all secrets and API keys"""
    allowed_passthrough = {
        'PATH', 'HOME', 'USER', 'SHELL', 'LANG', 'LC_ALL', 'TERM',
        'TMPDIR', 'XDG_RUNTIME_DIR', 'WSL_DISTRO_NAME', 'WSL_INTEROP'
    }

    clean_env = {}
    for key, value in os.environ.items():
        upper_key = key.upper()
        if any(secret_word in upper_key for secret_word in ['API_KEY', 'KEY', 'SECRET',
                                                            'PASSWORD', 'TOKEN',
                                                            'AUTH', 'CREDENTIALS']):
            continue
        if key in allowed_passthrough or key.startswith('LC_'):
            clean_env[key] = value

    return clean_env



class BaseCommandRunner:
    """Base runner managing process lifecycle, timeouts, process groups and truncation."""

    KILL_GRACE_SEC = 5

    def __init__(
            self,
            project_dir: str | Path,
            timeout_sec: int = 30,
            max_output_chars: int = 15000,
            ):
        self.project_dir = Path(project_dir).resolve()
        self.timeout_sec = timeout_sec
        self.max_output_chars = max_output_chars

        if not self.project_dir.exists():
            raise ValueError(
                f"Project directory does not exist: {self.project_dir}"
            )


    def _execute(self, argv: list[str], env: dict | None = None) -> CommandResult:
        """Execute a process with timeout, process-group isolation, and output truncation"""
        execution_env = env if env is not None else get_sanitized_env()
        try:
            process = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.project_dir),
                text = True,
                start_new_session=True,
                env=execution_env,
            )

        except Exception as e:
            return CommandResult(
                    returncode=-1,
                    stdout='',
                    stderr=f'Execution error {e}',
                    truncated=False,
                )

        try:
            stdout, stderr = process.communicate(timeout=self.timeout_sec)
            returncode = process.returncode
        
        except subprocess.TimeoutExpired:
            self._kill_process_group(process)

            try:
                stdout, stderr = process.communicate(timeout=self.KILL_GRACE_SEC)
            except subprocess.TimeoutExpired:
                stdout, stderr = '', ''

            message = f'Command timed out after {self.timeout_sec} seconds.'
            if stderr:
                message = f'{message}\n{stderr}'

            stdout, truncated = self._truncate(stdout)
            return CommandResult(
                returncode=-1,
                stdout=stdout,
                stderr=message,
                truncated=truncated,
            )

        stdout, truncated = self._truncate(stdout)
        return CommandResult(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            truncated=truncated,
        )


    def _kill_process_group(self, process: subprocess.Popen) -> None:
        """Kill the spawned process and its entire process tree"""
        try:
            pgid = os.getpgid(process.pid)
        except OSError:
            return

        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pgid, sig)
            except OSError:
                return

            try:
                process.wait(timeout=2)
                return
            except subprocess.TimeoutExpired:
                continue


    def _truncate(self, stdout: str) -> tuple[str, bool]:
        """Truncate stdout if it exceeds configured limit"""
        if len(stdout) <= self.max_output_chars:
            return stdout, False

        if self.max_output_chars <= 0:
            return '', True

        cut = stdout[:self.max_output_chars]
        return cut + '\n... (output truncated)', True


class HostRunner(BaseCommandRunner):
    """Run shell commands directly on the host with process group isolation."""


    def run(self, command: str) -> CommandResult:
        """Execute a bash command on the host"""
        return self._execute(['bash', '-c', command])


class SandboxRunner(BaseCommandRunner):
    """Run shell commands inside an isolated Firejail environment.

    FIREJAIL_SEEDS = {
        '.bashrc', '.bash_logout', '.profile', '.inputrc,
        '.Xauthority', '.config', '.local', '.cache'
    }
    """
    def __init__(
            self,
            project_dir: str | Path,
            timeout_sec: int = 30,
            max_output_chars: int = 15000,
            sandbox_home: str | Path | None = None,
        ):
        """Prepare the runner.

        Args:
            project_dir: Directory that bounds the sandbox.
            timeout_sec: Command timeout in seconds.
            max_output_chars: Maximum length of the returned stdout.
            sandbox_home: Path under which the project folder is visible
                inside the sandbox. Defaults to the home directory of the
                agent process, because Firejail's --private=DIR mounts DIR
                over the home path.

        Raises:
            ValueError: If project_dir does not exist.
        """
        super().__init__(project_dir, timeout_sec, max_output_chars)
        self.sandbox_home = Path(sandbox_home or os.path.expanduser('~'))


    def _cleanup_firejail_seeds(self, before_entries: set[str]) -> None:
        """Remove FIREJAIL_SEEDS from the sandbox"""
        import shutil
        try:
            current_entries = set(os.listdir(self.project_dir))
            created_by_firejail = (current_entries - before_entries) & self.FIREJAIL_SEEDS
            for entry in created_by_firejail:
                path = self.project_dir / entry
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.inlink(missung_ok=True)
        except Exception:
            pass
                    


    def run(self, command: str) -> CommandResult:
        """Execute a bash command inside the Firejail sandbox.

        Restrictions applied to the child process:

        * no network access at all (--net=none);
        * read-only root file system with a writable project directory;
        * seccomp filtering and caps on process count and CPU time;
        * a hard timeout and a cap on the amount of captured output.

        The command runs in its own session, so a timeout kills the sandbox
        together with every process it spawned.

        Args:
            command: Bash command line to execute.

        Returns:
            CommandResult with the exit code and captured streams. A
            timeout or sandbox failure is reported through the same object
            instead of raising an exception.
        """
        firejail_cmd = [
            'firejail',
            '--net=none',
            '--quiet',
            '--X11=none',
            '--nonewprivs',
            '--caps.drop=all',
            '--private-tmp',
            f'--private={self.project_dir}',
            '--read-only=/',
            f'--read-write={self.project_dir}',
            '--seccomp',
            # '--rlimit-nproc=100',
            f'--rlimit-cpu={self.timeout_sec + 5}',
            'bash',
            '-c',
            self._map_paths(command),
        ]

        before_entries = set(os.listdir(self.project_dir))

        env = get_sanitized_env()
        env['TMPDIR'] = '/var/tmp'

        result = self._execute(firejail_cmd, env)

        self._cleanup_firejail_seeds(before_entries)

        return result


    def _map_paths(self, command: str) -> str:
        """Rewrite host project paths so they resolve inside the sandbox.

        --private mounts the project folder over the home path, so the host
        path of the project does not exist in the sandbox while the sandbox
        home does. The model copies paths returned by
        get_current_directory, hence the rewrite.

        Args:
            command: Original command line.

        Returns:
            Command line with host project paths replaced by the sandbox
            home path.
        """
        real = str(self.project_dir)
        sandbox = str(self.sandbox_home)

        if real == sandbox:
            return command

        return command.replace(real, sandbox)


