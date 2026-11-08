"""Helpers for attaching project files to the chat context.

Files added through the /add command are read once, cached in memory and
prepended to the next user message, so the model sees their content without
spending a tool call on every turn.
"""

import os

MAX_FILE_SIZE = 500 * 1024


def read_project_file(file_path: str) -> str:
    """Read a text file that should be attached to the chat context.

    Args:
        file_path: Path to the file to read.

    Returns:
        File content decoded as UTF-8.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the path is not a regular file, exceeds the size
            limit or cannot be decoded as UTF-8 text.
    """
    clean_path = file_path.strip()
    if not os.path.exists(clean_path):
        raise FileNotFoundError(f'File not found: {clean_path}')

    if not os.path.isfile(clean_path):
        raise ValueError(f'Path is not a file: {clean_path}')

    file_size = os.path.getsize(clean_path)
    if file_size > MAX_FILE_SIZE:
        raise ValueError(
            f'File is too large: {file_size / 1024:.1f} KB. '
            f'Maximum allowed size: {MAX_FILE_SIZE / 1024:.1f} KB.'
        )

    try:
        with open(clean_path, 'r', encoding='utf-8') as f:
            content = f.read()
            return content
    except UnicodeDecodeError:
        raise ValueError(f'File is not a text file: {clean_path}')
    except Exception as e:
        raise ValueError(f'Error reading file: {e}')


class ProjectContext:
    """In-memory store of the project files attached to the chat.

    The content is cached on the first read, so the same file is not read
    from disk again on every request.
    """

    def __init__(self):
        """Create an empty file context."""
        self.active_files = {}


    def add(self, file_path: str) -> str:
        """Read a file and remember it as part of the chat context.

        Args:
            file_path: Path to the file to attach.

        Returns:
            Normalized path of the attached file.

        Raises:
            FileNotFoundError: If the path does not exist.
            ValueError: If the file cannot be read as text or is too large.
        """
        content = read_project_file(file_path)
        self.active_files[file_path.strip()] = content
        return file_path.strip()


    def drop(self, file_path: str) -> bool:
        """Detach a previously attached file.

        Args:
            file_path: Path of the file to detach.

        Returns:
            True when the file was attached, False otherwise.
        """
        clean_path = file_path.strip()
        if clean_path in self.active_files:
            del self.active_files[clean_path]
            return True
        return False


    def get_files_list(self) -> list:
        """List the paths of the attached files.

        Returns:
            Attached file paths in insertion order.
        """
        return list(self.active_files.keys())


    def get_combined_context(self) -> str:
        """Join the attached files into a single context block.

        Returns:
            Text block with every attached file and its content, or an
            empty string when nothing is attached.
        """
        if not self.active_files:
            return ''

        result = '\n--- Attached files of project ---\n'
        for file_path, content in self.active_files.items():
            result += f'--- {file_path} ---\n{content}\n'
        return result
