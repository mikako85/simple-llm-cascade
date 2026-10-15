from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    truncated: bool


class SandboxRunner:
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
            raise ValueError(f"Project directory does not exist: {self.project_dir}")


    def run(self, command: str) -> CommandResult:
        '''Выполняет bash-команду внутри изолированной среды Firejail.
        
        Ограничения:
            - Сеть полностью отключена (--net=none)
            - Чтение/Запись толькл проектная папка
            - Строгий таймаут и ограничения на размер выхлопа
        '''

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
            command
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

            # Защита контекста LLM от перегрузки огромным выводом
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
                stderr=f'System sandbox error: {str(e)}',
                truncated=False,
            )
                
        