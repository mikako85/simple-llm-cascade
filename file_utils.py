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


class ProjectContext:
    def __init__(self):
        self.active_files = {}


    def add(self, file_path: str) -> str:
        content = read_project_file(file_path)
        self.active_files[file_path.strip()] = content
        return file_path.strip()


    def drop(self, file_path: str) -> bool:
        clean_path = file_path.strip()
        if clean_path in self.active_files:
            del self.active_files[clean_path]
            return True
        return False


    def get_files_list(self) -> list:
        return list(self.active_files.keys())


    def get_combined_context(self) -> str:
        if not self.active_files:
            return ''

        result = '\n--- Attached files of project ---\n'
        for file_path, content in self.active_files.items():
            result += f'--- {file_path} ---\n{content}\n'
        return result

