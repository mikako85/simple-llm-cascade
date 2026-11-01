"""Implementations of the tools the agent is allowed to call.

The module wraps the local file system, the Firejail sandbox, DuckDuckGo
search and Crawl4AI page fetching behind plain functions. Every function
returns a string: the result is placed verbatim into the tool message of the
conversation history, so failures are reported as text instead of being
raised to the caller.
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

from crawl4ai import AsyncWebCrawler
from ddgs import DDGS

from sandbox_runner import SandboxRunner

# Working directory used by the sandbox: the folder that contains this file.
WORKSPACE_DIR = Path(__file__).parent.resolve()

# Shared sandbox runner with a short timeout, because tool results go
# straight into the model context.
sandbox_runner = SandboxRunner(project_dir=WORKSPACE_DIR, timeout_sec=30)


def _resolve_safe_path(path: str) -> Path:
    """Resolve a path safely within WORKSPACE_DIR.

    Args:
        path: Relative path to resolve.

    Returns:
        Absolute path within WORKSPACE_DIR.
    """
    if not path or not path.strip():
        raise ValueError('File path cannot be empty')

    raw_path = Path(path.strip()).expanduser()

    if not raw_path.is_absolute():
        resolved_path = (WORKSPACE_DIR / raw_path).resolve()
    else:
        resolved_path = raw_path.resolve()

    if not resolved_path.is_relative_to(WORKSPACE_DIR):
        raise PermissionError(
            f'Sandbox security violation: Path ""{path}" is not a child of "{WORKSPACE_DIR}"'
            f'. Use relative paths or $HOME. Access Denied.'
        )

    if '.git' in resolved_path.parts:
        raise PermissionError(
            f'Sandbox security violation: Path ""{path}" contains ".git" in its path. Access Denied.'
        )

    return resolved_path


def run_bash_command(command: str) -> str:
    """Execute a bash command inside the isolated Firejail sandbox.

    The sandbox runs without network access, confines writes to the project
    directory and enforces CPU, process and time limits.

    Inside the sandbox the project folder is mounted as $HOME, so the host
    path reported by get_current_directory() does not exist there. Prefer
    relative paths or $HOME; absolute project paths are rewritten
    automatically.

    Args:
        command: Bash command line to execute.

    Returns:
        Formatted report with STDOUT, STDERR and the exit code of the
        command. Sandbox failures are reported in the same shape.
    """
    result = sandbox_runner.run(command)

    output = []
    if result.stdout:
        output.append(f'STDOUT:\n{result.stdout}')
    if result.stderr:
        output.append(f'STDERR:\n{result.stderr}')
    output.append(f'Exit code: {result.returncode}')
    return '\n'.join(output)


def get_current_directory() -> str:
    """Return the current working directory of the agent process.

    Returns:
        Absolute path to the current working directory of the agent process.
        This is a host path; inside the sandbox the project folder is
        mounted as $HOME instead.
    """
    return os.getcwd()


def get_system_time() -> str:
    """Return the current local date and time.

    Returns:
        String representation of datetime.now().
    """
    return str(datetime.now())


def read_text_document(path: str, max_kb: int = 100) -> str:
    """Read a UTF-8 encoded text file from disk.

    Args:
        path: Path to the text document.
        max_kb: Maximum allowed file size in kilobytes.

    Returns:
        File content, or a human-readable error message when the file is
        missing, too large or cannot be read.
    """
    try:
        if not os.path.exists(path):
            return f"File not found: {path}"

        file_size_kb = os.path.getsize(path) / 1024

        if file_size_kb > max_kb:
            return f"File size exceeds {max_kb} KB"
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            return content if content else 'File is empty'
    except Exception as e:
        return f"Read error: {e}"


def write_file(path: str, content: str):
    """Write or overwrite a tect file with the provided content.

    Automatically creates the parent directory if it does not exist.

    Args:
        path (str): Path to the target file (relative or absolute).
        content (str): Text content to write into the file.

    Returns:
        Confirmation message with stats, or an error description.
    """
    try:
        target_path = _resolve_safe_path(path)
        if target_path.exists() and target_path.is_dir():
            return f'Error: Path "{path}" is an existing_directory, not a file'


        target_path.parent.mkdir(parents=True, exist_ok=True)

        is_overwrite = target_path.exists()

        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(content)

        lines_count = len(content.splitlines())
        chars_count = len(content)
        action = 'overwritten' if is_overwrite else 'created'
        return (
            f'File {path} succesfully {action} '
            f'{lines_count} lines and {chars_count} characters written'
        )

    except PermissionError:
        return f'Permission denied: {path}'
    except Exception as e:
        return f'Write error: {e}'

       





def search_web(query: str, max_results: int = 5) -> str:
    """Search the web with DuckDuckGo and format the results.

    Args:
        query: Search query in natural language.
        max_results: Maximum number of results to return.

    Returns:
        Numbered list of results, each with a title, a URL and a snippet.
        A short message is returned when nothing was found or on error.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return "No results found"

            formatted_results = []
            for i, r in enumerate(results):
                title = r.get('title', 'Untitled')
                href = r.get('href', '#')
                body = r.get('body', 'No description')
                formatted_results.append(f"{i + 1}. {title} - {href}\n{body}\n")

            return "\n".join(formatted_results)
    except Exception as e:
        return f"Search error: {e}"


def list_directory(path: str = '.') -> str:
    """List the entries of a directory.

    Args:
        path: Directory path, absolute or relative.

    Returns:
        Newline-separated entry names sorted alphabetically, with a trailing
        slash for directories. An error message is returned when the path
        does not exist or is not a directory.
    """
    try:
        target_path = Path(path).resolve()
        if not target_path.exists():
            return f'Directory not found: {path}'
        if not target_path.is_dir():
            return f'Path is not a directory: {path}'
        items = []
        for entry in sorted(target_path.iterdir()):
            name = f'{entry.name}/' if entry.is_dir() else entry.name
            items.append(name)
        return '\n'.join(items) if items else 'Empty directory'
    except Exception as e:
        return f'Directory listing error: {e}'


def fetch_url_markdown(url: str) -> str:
    """Fetch a web page and convert it to Markdown.

    JavaScript is executed during rendering, so single-page applications are
    supported. The crawler is asynchronous and is driven through
    asyncio.run to keep the tool interface synchronous.

    Args:
        url: Direct URL of the page to parse.

    Returns:
        Page content as raw Markdown, or an error message when the page
        could not be loaded.
    """
    async def _crawl():
        """Render the page and return its Markdown or an error text."""
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url)
            if result.success:
                return result.markdown.raw_markdown
            else:
                return f'Page loading error: {result.error_message}'

    try:
        return asyncio.run(_crawl())
    except Exception as e:
        return f'Crawl4AI initialization error: {e}'

