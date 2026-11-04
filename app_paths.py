import os
from pathlib import Path

APP_DATA_DIR = Path.home() / '.simple-llm-cascade'
CONFIG_FILE = APP_DATA_DIR / 'models.yaml'
ENV_FILE = APP_DATA_DIR / '.env'
MEMORY_DIR = APP_DATA_DIR / 'memory'
SESSIONS_DIR = MEMORY_DIR / 'sessions'
GLOBAL_PROMPT_FILE = MEMORY_DIR / 'SYSTEM_PROMPT.md'


def ensure_app_dirs_exist():
    """Guarantee the existence of the app data directory."""
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)