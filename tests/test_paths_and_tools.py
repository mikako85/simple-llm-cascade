from pathlib import Path
import pytest

from policy import ExecutionMode
import tools


class TestsafePathResolution:
    """Testing the _resolve_safe_path function and file system barriers"""


    def test_workspace_relative_path_allowed(self):
        """Standard relative paths within a project should resolve successfully"""
        tools.set_execution_mode(ExecutionMode.ASK)
        resolved = tools._resolve_safe_path('src/module.py')
        assert resolved.is_relative_to(tools.WORKSPACE_DIR)
        assert resolved.name == 'module.py'


    @pytest.mark.parametrize('env_filename', [
        '.env',
        '.env.production',
        'secrets.env',
        '.env_backup',
        '.env.local',
        ])
    def test_env_files_strictly_forbidden(self, env_filename: str):
        """Access to ANY environment/secrets files must raise a PermissionError."""
        tools.set_execution_mode(ExecutionMode.ASK)
        with pytest.raises(PermissionError) as exc_info:
            tools._resolve_safe_path(env_filename)
        assert 'Security policy violation' in str(exc_info.value)


    @pytest.mark.parametrize('sensitive_path',[
        '~/.ssh/id_rsa',
        '~/.aws/credentials',
        '~/.gnupg/secring.gpg',
        '~/.bashrc',
        '~/.zshrc',
        '~/.simple-llm-cascade/models.yaml',
        '~/.simple-llm-cascade/.env',
        '/etc/passwd',
        '/etc/shadow',
        '/boot/vmlinuz',
        '/sys/class/net',
    ])
    def test_sensitive_system_and_home_targets_blocked(self, sensitive_path: str):
        """Access to system directories and user secrets is blocked"""
        tools.set_execution_mode(ExecutionMode.ASK)
        with pytest.raises(PermissionError) as exc_info:
            tools._resolve_safe_path(sensitive_path)
        assert 'Security policy violation' in str(exc_info.value)


    def test_git_internal_path_blocked(self):
        """Access to the contents of .git is blocked."""
        tools.set_execution_mode(ExecutionMode.ASK)
        with pytest.raises(PermissionError) as exc_info:
            tools._resolve_safe_path('.git')
        assert 'Sandbox security violation' in str(exc_info.value)


    def test_sandbox_mode_strictly_confines_to_workspace(self, tmp_path):
        """Sandbox mode should prevent access to anything outside of the workspace."""
        tools.set_execution_mode(ExecutionMode.SANDBOX)
        outside_path = str(tmp_path / 'outside_file.txt')
        with pytest.raises(PermissionError) as exc_info:
            tools._resolve_safe_path(str(outside_path))
        assert 'Sandbox security violation' in str(exc_info.value)


class TestRunnerModeTransitions:
    """Verification of mode switching and runner restoration"""


    def test_mode_transitions_switch_runners_corrextly(self):
        """We verify that switching from sandbox -> ask and from sandbox -> yolo restores HostRunner."""
        tools.set_execution_mode(ExecutionMode.SANDBOX)
        assert tools.current_execution_mode == ExecutionMode.SANDBOX
        assert tools.active_runner == tools._sandbox_runner

        tools.set_execution_mode(ExecutionMode.ASK)
        assert tools.current_execution_mode == ExecutionMode.ASK
        assert tools.active_runner == tools._host_runner

        tools.set_execution_mode(ExecutionMode.SANDBOX)
        assert tools.active_runner == tools._sandbox_runner

        tools.set_execution_mode(ExecutionMode.YOLO)
        assert tools.current_execution_mode == ExecutionMode.YOLO
        assert tools.active_runner == tools._host_runner


class TestFileOperationSAfety:
    """Verifying safe file reading and writing"""
    def test_write_file_and_read_text_document_roundtrip(self, tmp_path, monkeypatch):
        """Verifying correct file writing and reading using tools"""
        monkeypatch.setattr(tools, 'WORKSPACE_DIR', tmp_path)
        tools.set_execution_mode(ExecutionMode.ASK)

        test_file = 'subfolder/hello.txt'
        test_content = 'Hello from pytest safe runner!'

        write_result = tools.write_file(test_file, test_content)
        assert 'successfully created' in write_result

        read_result = tools.read_text_document(test_file)
        assert read_result == test_content


    def test_read_text_document_vlocks_secrets(self):
        """The file-reading tool should provide a clear security error when an attempt is made to read secrets."""
        tools.set_execution_mode(ExecutionMode.ASK)
        result = tools.read_text_document('.env')
        assert 'Security policy violation' in result


    def test_write_file_blocks_secrets(self):
        """The recording tool must not allow system files to be overwritten."""
        tools.set_execution_mode(ExecutionMode.ASK)
        result = tools.write_file('/etc/hosts', '127.0.0.1 malicious')        
        assert 'Security Error' in result or 'Security policy violation' in result

