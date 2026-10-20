import os

MAX_FILE_SIZE = 500 * 1024

def read_project_file(file_path: str) -> str:
    '''Safe reads the text_file and put it on context'''

    clean_path = file_path.strip()
    if not os.path.exists(clean_path):
        raise FileNotFoundError(f' file Not Found: {clean_path}')

    if not os.path.isfile(clean_path):
        raise ValueError(f'Path is not a file: {clean_path}')

    file_size = os.path.getsize(clean_path)
    if file_size > MAX_FILE_SIZE:
        raise ValueError(
            f'File is too large: {file_size / 1024:.1f} KB.) '
            f'Maximum allowed size: {MAX_FILE_SIZE / 1024:.1f} KB.'
        )

    try:
        with open(clean_path, 'r', encoding='utf-8') as f:
            content = f.read()
            return content
    except UnicodeDecodeError:
        raise ValueError(f'File is not text file: {clean_path}')
    except Exception as e:
        raise ValueError(f'Error reading file: {e}')

print(read_project_file('2025-06-30_08-50.png'))