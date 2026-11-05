import os
from pathlib import Path

APP_DATA_DIR = Path.home() / '.simple-llm-cascade'
CONFIG_FILE = APP_DATA_DIR / 'models.yaml'
ENV_FILE = APP_DATA_DIR / '.env'
MEMORY_DIR = APP_DATA_DIR / 'memory'
SESSIONS_DIR = MEMORY_DIR / 'sessions'
GLOBAL_PROMPT_FILE = MEMORY_DIR / 'SYSTEM_PROMPT.md'


def get_config_file() -> Path:
    """Find local models.yaml in current directory, if no - get global"""
    local_config = Path.cwd() / 'models.yaml'
    if local_config.exists() and local_config.stat().st_size > 0:
        return local_config
    return CONFIG_FILE


def get_env_file() -> Path:
    """Find local .env in current directory, if no - get global"""
    local_env = Path.cwd() / '.env'
    if local_env.exists() and local_env.stat().st_size > 0:
        return local_env
    return ENV_FILE


def ensure_app_dirs_exist():
    """Guarantee the existence of the app data directory."""
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)