import os
import subprocess
from pathlib import Path


def _edit_system_prompt_interactive():
    '''Edits the system prompt interactively'''
    prompt_path = Path('memory/SYSTEM_PROMPT.md')

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
                print(f'System prompt editing failed. code - {result.returncode}')
            success = True
            break
        except FileNotFoundError:
            print(f'Editor {editor} not found. Skipping...')
        except Exception as e:
            print(f'Error editing system prompt: {e}')
            continue

    if not success:
        print('Do not find any editor in the system.')
        print(f'You can edit the system prompt manually: {prompt_path.absolute()}')
    