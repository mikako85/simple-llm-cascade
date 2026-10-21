"""Execution of shell commands inside a Firejail sandbox.

The runner wraps every command in a Firejail profile with network access
disabled, a private home directory and read-write access limited to the
project folder. Output is truncated before it reaches the model, so a noisy
command cannot flood the context window.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a sandboxed command.

    Attributes:
        returncode: Exit code of the command, or -1 when the sandbox itself
            failed or the command timed out.
        stdout: Captured standard output, possibly truncated.
        stderr: Captured standard error.
        truncated: True when stdout exceeded the configured limit.
    """

    returncode: int
    stdout: str
    stderr: str
    truncated: bool


class SandboxRunner:
    """Run shell commands inside an isolated Firejail environment.

    Attributes:
        project_dir: Absolute path of the only directory the command may
            write to.
        timeout_sec: Hard wall-clock limit for a single command.
        max_output_chars: Limit applied to stdout before it is returned.
    """

    def __init__(
            self,
            project_dir: str | Path,
            timeout_sec: int = 30,
            max_output_chars: int = 15000,
        ):
        """Prepare the runner.

        Args:
            project_dir: Directory that bounds the sandbox.
            timeout_sec: Command timeout in seconds.
            max_output_chars: Maximum length of the returned stdout.

        Raises:
            ValueError: If project_dir does not exist.
        """
        self.project_dir = Path(project_dir).resolve()
        self.timeout_sec = timeout_sec
        self.max_output_chars = max_output_chars

        if not self.project_dir.exists():
            raise ValueError(f"Project directory does not exist: {self.project_dir}")


    def run(self, command: str) -> CommandResult:
        """Execute a bash command inside the Firejail sandbox.

        Restrictions applied to the child process:

        * no network access at all (--net=none);
        * read-only root file system with a writable project directory;
        * seccomp filtering and caps on process count and CPU time;
        * a hard timeout and a cap on the amount of captured output.

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
            f'--private={self.project_dir}',
            '--read-only=/',
            f'--read-write={self.project_dir}',
            '--seccomp',
            '--rlimit-nproc=100',
            f'--rlimit-cpu={self.timeout_sec}',
            'bash',
            '-c',
            command,
        ]

        try:
            process = subprocess.run(
                firejail_cmd,
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
            )

            stdout = process.stdout
            stderr = process.stderr
            truncated = False

            # Keep a huge output from flooding the model context window.
            if len(stdout) > self.max_output_chars:
                stdout = (
                    stdout[:self.max_output_chars]
                    + '\n... (output truncated)'
                )
                truncated = True

            return CommandResult(
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                truncated=truncated,
            )

        except subprocess.TimeoutExpired:
            return CommandResult(
                returncode=-1,
                stdout='',
                stderr=(f'Command timed out after {self.timeout_sec} seconds'),
                truncated=False,
            )
        except Exception as e:
            return CommandResult(
                returncode=-1,
                stdout='',
                stderr=f'System sandbox error: {e}',
                truncated=False,
            )
