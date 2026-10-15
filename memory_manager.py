import os
import json
from datetime import datetime

MEMORY_DIR = 'memory'
SESSIONS_DIR = os.path.join(MEMORY_DIR, 'sessions')
MEMORY_FILE = os.path.join(MEMORY_DIR, 'MEMORY.md')


class MemoryManager:
    def __init__(self):
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        if not os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
                f.write('# ПРоектная память агента\n\n Здесь хранаится контекст и важные детали. \n') 

        self.current_session_file = None


    def load_global_memory(self) -> str:
        """Считывает долговременную память из MEMORY.md"""
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        return ''


    def list_sessions(self) -> list:
        '''Возвращает список всех сессий'''
        if not os.path.exists(SESSIONS_DIR):
            return []
        files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.jsonl')]
        return sorted(files, reverse=True)


    def save_dialogue_to_file(self, messages: list, session_name: str = None) -> str:
        '''Сохраняет диалог в файл сессии'''
        if not session_name or not session_name.strip():
            session_name = datetime.now().strftime('%Y-%m-%d_%H-%M-%S.jsonl')

        if not session_name.endswith('.jsonl'):
            session_name += '.jsonl'

        full_path = os.path.join(SESSIONS_DIR, session_name)
        self.current_session_file = full_path

        with open(full_path, 'w', encoding='utf-8') as f:
            for msg in messages:
                f.write(json.dumps(msg, ensure_ascii=False ) + '\n')

        return session_name


    def load_existing_session(self, session_name: str):
        '''Загружает существующий файл сессии и возвращает список сообщений для восстановления контекста'''
        full_path = os.path.join(SESSIONS_DIR, session_name)

        if not os.path.exists(full_path):
            raise FileNotFoundError(f'Файл сессии не найден: {full_path}')

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
        '''Удаляет файл сессии по имени'''
        full_path = os.path.join(SESSIONS_DIR, session_name)
        if os.path.exists(full_path):
            os.remove(full_path)
            if self.current_session_file == full_path:
                self.current_session_file = None
            return True
        return False
