"""Execution of shell commands inside a Firejail sandbox.

The runner wraps every command in a Firejail profile with network access
disabled, a private home directory and read-write access limited to the
project folder. Output is truncated before it reaches the model, so a noisy
command cannot flood the context window.
"""

import os
import signal
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
        sandbox_home: Path the project folder is mounted at inside the
            sandbox, i.e. the home directory of the sandboxed process.
        timeout_sec: Hard wall-clock limit for a single command.
        max_output_chars: Limit applied to stdout before it is returned.
    """

    # Time allowed for the pipes to drain after the sandbox has been killed,
    # so a wedged grandchild cannot hang the runner.
    KILL_GRACE_SEC = 5

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
        self.project_dir = Path(project_dir).resolve()
        self.sandbox_home = Path(sandbox_home or os.path.expanduser('~'))
        self.timeout_sec = timeout_sec
        self.max_output_chars = max_output_chars

        if not self.project_dir.exists():
            raise ValueError(
                f"Project directory does not exist: {self.project_dir}"
            )


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

        # /tmp is mounted read-only, but many tools insist on a writable
        # temporary directory, so point them at the writable /var/tmp.
        env = dict(os.environ)
        env['TMPDIR'] = '/var/tmp'

        try:
            process = subprocess.Popen(
                firejail_cmd,
                cwd=str(self.project_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                # Own process group, so the whole process tree stays
                # killable as one unit.
                start_new_session=True,
            )
        except Exception as e:
            return CommandResult(
                returncode=-1,
                stdout='',
                stderr=f'System sandbox error: {e}',
                truncated=False,
            )

        try:
            stdout, stderr = process.communicate(timeout=self.timeout_sec)
            returncode = process.returncode

        except subprocess.TimeoutExpired:
            self._kill_process_group(process)

            # Collect whatever the command managed to write before the kill.
            try:
                stdout, stderr = process.communicate(
                    timeout=self.KILL_GRACE_SEC
                )
            except subprocess.TimeoutExpired:
                stdout, stderr = '', ''

            message = f'Command timed out after {self.timeout_sec} seconds'
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


    def _kill_process_group(self, process: subprocess.Popen) -> None:
        """Kill the sandbox and every process it spawned.

        A subprocess timeout only terminates the direct child, while
        background jobs started by the command keep running and hold the
        output pipes open. The child is started in its own session, which
        makes the whole tree killable with a single signal.

        Args:
            process: Sandbox process to terminate.
        """
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
        """Cut captured output down to max_output_chars.

        Args:
            stdout: Raw captured standard output.

        Returns:
            Tuple of the (possibly shortened) text and a truncation flag.
        """
        if len(stdout) <= self.max_output_chars:
            return stdout, False

        if self.max_output_chars <= 0:
            return '', True

        cut = stdout[:self.max_output_chars]
        return cut + '\n... (output truncated)', True
