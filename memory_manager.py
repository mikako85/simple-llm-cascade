"""Long-term memory and dialogue session persistence.

The agent keeps two kinds of memory:

* a global memory file (memory/SYSTEM_PROMPT.md) injected into the system
  prompt at start-up;
* per-session transcripts stored as JSON Lines files under
  memory/sessions, one JSON object per message.
"""

import json
import os
from datetime import datetime

from app_paths import MEMORY_DIR, SESSIONS_DIR, GLOBAL_PROMPT_FILE

# MEMORY_DIR = 'memory'
# SESSIONS_DIR = os.path.join(MEMORY_DIR, 'sessions')
# MEMORY_FILE = os.path.join(MEMORY_DIR, 'SYSTEM_PROMPT.md')

DEFAULT_MEMORY_TEMPLATE = (
    '# Agent project memory\n\n'
    'This file stores the long-term context and important project details.\n'
)


class MemoryManager:
    """Manage the global memory file and the saved dialogue sessions.

    The manager creates the memory directory layout on initialization and
    keeps track of the session file currently in use.
    """

    def __init__(self):
        """Create the memory folders and the memory file when missing."""
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        if not GLOBAL_PROMPT_FILE.exists():
            with open(GLOBAL_PROMPT_FILE, 'w', encoding='utf-8') as f:
                f.write(DEFAULT_MEMORY_TEMPLATE)

        self.current_session_file = None


    def load_global_memory(self) -> str:
        """Read the long-term memory from SYSTEM_PROMPT.md.

        Returns:
            Content of the memory file, or an empty string when the file
            does not exist.
        """
        if GLOBAL_PROMPT_FILE.exists():
            with open(GLOBAL_PROMPT_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        return ''

    def list_sessions(self) -> list:
        """List the available dialogue sessions.

        Returns:
            Session file names ending with .jsonl, newest first.
        """
        if not os.path.exists(SESSIONS_DIR):
            return []
        files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.jsonl')]
        return sorted(files, reverse=True)


    def save_dialogue_to_file(self, messages: list, session_name: str = None) -> str:
        """Write the dialogue to a session file.

        Args:
            messages: Conversation messages in OpenAI chat format.
            session_name: Target session name. A timestamp-based name is
                generated when the argument is empty. The .jsonl extension
                is appended automatically.

        Returns:
            Name of the written session file.
        """
        if not session_name or not session_name.strip():
            session_name = datetime.now().strftime('%Y-%m-%d_%H-%M-%S.jsonl')

        if not session_name.endswith('.jsonl'):
            session_name += '.jsonl'

        full_path = os.path.join(SESSIONS_DIR, session_name)
        self.current_session_file = full_path

        with open(full_path, 'w', encoding='utf-8') as f:
            for msg in messages:
                f.write(json.dumps(msg, ensure_ascii=False) + '\n')

        return session_name


    def load_existing_session(self, session_name: str):
        """Load a saved session and rebuild the message history.

        Args:
            session_name: Name of the session file to load.

        Returns:
            List of messages parsed from the session file. Malformed lines
            are skipped silently.

        Raises:
            FileNotFoundError: If the session file does not exist.
        """
        full_path = os.path.join(SESSIONS_DIR, session_name)

        if not os.path.exists(full_path):
            raise FileNotFoundError(f'Session file not found: {full_path}')

        self.current_session_file = full_path
        messages = []

        with open(full_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        return messages


    def delete_session(self, session_name: str) -> bool:
        """Delete a session file.

        Args:
            session_name: Name of the session file to delete.

        Returns:
            True when the file was removed, False when it was not found.
        """
        full_path = os.path.join(SESSIONS_DIR, session_name)
        if os.path.exists(full_path):
            os.remove(full_path)
            if getattr(self, 'current_session_file', None) == full_path:
                self.current_session_file = None
            return True
        return False
