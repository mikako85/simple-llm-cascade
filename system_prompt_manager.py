"""Editing of the global system prompt from the CLI.

The /prompt command opens memory/SYSTEM_PROMPT.md in an external editor.
The file is injected into the system message on the next agent start.
"""

import os
import subprocess
from app_paths import GLOBAL_PROMPT_FILE


def _edit_system_prompt_interactive():
    """Open the system prompt file in the first available editor.

    The editor is taken from the EDITOR environment variable, with nano,
    vim and vi tried as fallbacks. When no editor is available the path to
    the file is printed so the user can edit it manually.

    Returns:
        None
    """
    prompt_path = GLOBAL_PROMPT_FILE

    prompt_path.parent.mkdir(parents=True, exist_ok=True)

    if not prompt_path.exists():
        prompt_path.write_text('', encoding='utf-8')

    editors_to_try = []

    if os.environ.get('EDITOR'):
        editors_to_try.append(os.environ['EDITOR'])

    editors_to_try.extend(['nano', 'vim', 'vi'])

    success = False
    for editor in editors_to_try:
        try:
            result = subprocess.run([editor, prompt_path], check=True)
            if result.returncode == 0:
                print('System prompt edited successfully.')
            else:
                print(f'System prompt editing failed. Code: {result.returncode}')
            success = True
            break
        except FileNotFoundError:
            print(f'Editor {editor} not found. Skipping...')
        except Exception as e:
            print(f'Error editing system prompt: {e}')
            continue

    if not success:
        print('No supported editor found in the system.')
        print(f'You can edit the system prompt manually: {prompt_path.absolute()}')
