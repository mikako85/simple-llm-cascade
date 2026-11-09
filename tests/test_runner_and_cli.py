import os
import pytest
from sandbox_runner import get_sanitized_env
from cli_controller import parse_cli_args

class TestEnvironmentSanitization:
    """Testing the clearing of environment variables to prevent key leakage"""

    def test_secrets_and_api_keys_are_stripped(self, monkeypatch):
        """Any variables containing KEY, TOKEN, SECRET, or PASSWORD must be filtered out."""
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-secret-12345')
        monkeypatch.setenv('GEMINI_API_KEY', 'AIzaSy-secret-67890')
        monkeypatch.setenv('GITHUB_TOKEN', 'ghp_topsecrettoken')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'super_secret_aws')
        monkeypatch.setenv('DATABASE_PASSWORD', 'admin123')
        monkeypatch.setenv('APP_CREDENTIALS', 'creds.json')
        monkeypatch.setenv('RANDOM_SECRET_VAR', 'classified')

        # А также системные переменные, которые ДОЛЖНЫ остаться
        monkeypatch.setenv('PATH', '/usr/local/bin:/usr/bin:/bin')
        monkeypatch.setenv('HOME', '/home/testuser')
        monkeypatch.setenv('USER', 'testuser')

        sanitized = get_sanitized_env()

        for key in sanitized.keys():
            upper = key.upper()
            assert 'KEY' not in upper
            assert 'TOKEN' not in upper
            assert 'SECRET' not in upper
            assert 'PASSWORD' not in upper
            assert 'CREDENTIALS' not in upper

        assert sanitized.get('PATH') == '/usr/local/bin:/usr/bin:/bin'
        assert sanitized.get('HOME') == '/home/testuser'
        assert sanitized.get('USER') == 'testuser'


class TestCLIArdumentParsing:
    """Testing flags of command line"""

    def test_explicit_mode_flag(self, monkeypatch):
        """The --mode <value> flag should be parsed correctly"""
        monkeypatch.setattr('sys.argv', ['cascade', '--mode', 'yolo'])
        assert parse_cli_args() == "yolo"

        monkeypatch.setattr('sys.argv', ['cascade', '-m', 'sandbox'])
        assert parse_cli_args() == "sandbox"

        monkeypatch.setattr('sys.argv', ['cascade', '--mode', 'ask'])
        assert parse_cli_args() == "ask"


    def test_shorthand_boolean_flags(self, monkeypatch):
        """The flags -y, --yolo, -a, --ask, -s, and --sandbox should work."""
        monkeypatch.setattr('sys.argv', ['cascade', '-y'])
        assert parse_cli_args() == 'yolo'

        monkeypatch.setattr('sys.argv', ['cascade', '--yolo'])
        assert parse_cli_args() == 'yolo'

        monkeypatch.setattr('sys.argv', ['cascade', '-a'])
        assert parse_cli_args() == 'ask'

        monkeypatch.setattr('sys.argv', ['cascade', '--ask'])
        assert parse_cli_args() == 'ask'

        monkeypatch.setattr('sys.argv', ['cascade', '-s'])
        assert parse_cli_args() == 'sandbox'

        monkeypatch.setattr('sys.argv', ['cascade', '--sandbox'])
        assert parse_cli_args() == 'sandbox'


    def test_no_arguments_returns_none(self, monkeypatch):
        """If no flags are provided, None should be returned"""
        monkeypatch.setattr('sys.argv', ['cascade'])
        assert parse_cli_args() is None


    def test_conflicting_mode_flags_raise_error(self, monkeypatch):
        """If conflicting flags are provided, an error should be raised"""
        monkeypatch.setattr('sys.argv', ['cascade', '-y', '-a'])
        with pytest.raises(SystemExit):
            parse_cli_args()

       