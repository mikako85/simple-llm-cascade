import os
from datetime import datetime
from pathlib import Path
import asyncio
from ddgs import DDGS
from crawl4ai import AsyncWebCrawler
from sandbox_runner import SandboxRunner

#define workdir sandbox
WORKSPACE_DIR = Path(__file__).parent.resolve()

#define sandbox runner
sandbox_runner = SandboxRunner(project_dir=WORKSPACE_DIR, timeout_sec=10)

def run_bash_command(command: str) -> str:
    '''Выполняет bash-команду внутри изолированной среды Firejail.'''

    result = sandbox_runner.run(command)

    output = []
    if result.stdout:
        output.append(f'STDOUT:\n{result.stdout}')
    if result.stderr:
        output.append(f'STDERR:\n{result.stderr}')
    output.append(f'Exit code: {result.returncode}')
    return '\n'.join(output)



def get_current_directory() -> str:
    return os.getcwd()


def get_system_time() -> str:
    return str(datetime.now())


def read_text_document(path: str, max_kb: int = 100) -> str:
    try:
        if not os.path.exists(path):
            return f"Файл не найден: {path}"

        file_size_kb = os.path.getsize(path) / 1024

        if file_size_kb > max_kb:
            return f"Размер файла превышает {max_kb} КБ"
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            return content if content else 'Файл пуст'
    except Exception as e:
        return f"Произошла ошибка чтения: {e}"


def search_web(query: str, max_results: int = 5) -> str:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return "Ничего не нашлось"

            formatted_results = []
            for i, r in enumerate(results):
                title = r.get('title', 'Без заголовка')
                href = r.get('href', '#')
                body = r.get('body', 'Нет описания')
                formatted_results.append(f"{i + 1}. {title} - {href}\n{body}\n")

            return "\n".join(formatted_results)
    except Exception as e:
        return f"Произошла ошибка поиска: {e}"


def list_directory(path: str = '.') -> str:
    '''Возвращает список файлов по указанному пути.'''
    try:
        target_path = Path(path).resolve()
        if not target_path.exists():
            return f'Директория не найдена: {path}'
        if not target_path.is_dir():
            return f'Путь не является директорией: {path}'
        items = []
        for entry in sorted(target_path.iterdir()):
            name = f'{entry.name}/' if entry.is_dir() else entry.name
            items.append(name)
        return '\n'.join(items) if items else 'Пустая директория'
    except Exception as e:
        return f'Произошла ошибка при листинге директории: {e}'


def fetch_url_markdown(url: str) -> str:
    '''Загружает страницу через CrawlAI и возвращает содержимое в формате Markdown.'''
    async def _crawl():
        async with AsyncWebCrawler(verbose=False)  as crawler:
            result = await crawler.arun(url=url)
            if result.success:
                return result.markdown.raw_markdown
            else:
                return f'Произошла ошибка при загрузке страницы: {result.error_message}'

    try:
        return asyncio.run(_crawl())
    except Exception as e:
        return f'Произошла ошибка при инициализации Crawl4AI: {e}'
            