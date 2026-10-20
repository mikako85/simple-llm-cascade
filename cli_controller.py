import os
import yaml
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from agent import ChatAgent
from config_wizard import ConfigWizard
from system_prompt_manager import _edit_system_prompt_interactive
import config


class AppCLIController:
    '''controller for global system commands (by example /config)'''
    def __init__(self, agent: ChatAgent):
        self.agent = agent

    def show_models_status(self):
        '''Считывает и выводит статус моделей, фолбэков и дефолтного маршрута из models.yaml'''
        config_path = "models.yaml"
        
        if not os.path.exists(config_path):
            print("❌ Файл конфигурации models.yaml не найден.")
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            print(f"❌ Ошибка чтения конфига: {e}")
            return

        settings = data.get("settings", {})
        models = data.get("models", [])
        fallbacks = data.get("fallbacks", [])
        default_route = settings.get("default_route", "Не задано")

        box_width = 58  # Фиксированная ширина внутренней части рамки

        print('\n╔' + '═' * box_width + '╗')
        title = "СТАТУС МОДЕЛЕЙ И ФОЛБЭКОВ"
        print(f'║ {title:^{box_width-2}} ║')
        print('╠' + '═' * box_width + '╣')
        
        route_str = f"⭐ Активный маршрут: {default_route}"
        print(f'║ {route_str:<{box_width-2}} ║')
        print('╠' + '─' * box_width + '╣')
        
        print(f'║ Доступные модели в конфиге:{"":<{box_width-2-28}} ║')
        for m in models:
            m_name = m.get("model_name", "unknown")
            litellm = m.get("litellm_model", "")
            marker = " (active)" if m_name == default_route else ""
            line1 = f"  • {m_name}{marker}"
            print(f'║ {line1:<{box_width-2}} ║')
            
            if litellm:
                # Если строка с литлм моделью слишком длинная, аккуратно обрежем её
                if len(litellm) > box_width - 6:
                    litellm = litellm[:box_width-9] + "..."
                line2 = f"    ({litellm})"
                print(f'║ {line2:<{box_width-2}} ║')

        if fallbacks:
            print('╠' + '─' * box_width + '╣')
            print(f'║ Цепочки фолбэков:{"":<{box_width-2-17}} ║')
            for fb in fallbacks:
                primary = fb.get("primary", "")
                chain = ", ".join(fb.get("chain", []))
                line_fb = f"  {primary} ➔ [{chain}]"
                print(f'║ {line_fb:<{box_width-2}} ║')
                
        print('╚' + '═' * box_width + '╝\n')

    def handle_command(self, user_input: str) -> bool:
        '''handle system command, returns True if command was handled'''
        if user_input.strip() == '/config':
            wizard = ConfigWizard()
            wizard.run()
            return True

        if user_input.strip() == '/models':
            self.show_models_status()
            return True

        if user_input.strip() == '/prompt':
            _edit_system_prompt_interactive()
            return True

        

        if user_input.startswith('/add'):
            file_path = user_input[len('/add'):].strip()
            if not file_path:
                print('Please, specify the path to the file')
                return True
            try:
                self.agent.context.add(file_path)
                print(f'File {file_path} added to context')
            except Exception as e:
                print(f'Error adding file to context: {e}')
            return True

        if user_input.startswith('/drop'):
            file_path = user_input[len('/drop'):].strip()
            if not file_path:
                print('Please, specify the path to the file')
                return True

            removed = self.agent.context.drop(file_path)
            if removed:
                print(f'File {file_path} removed from context')
            else:
                print(f'File {file_path} not found in context')
            return True

        if user_input.startswith('/files'):
            files = self.agent.context.get_files_list()
            if not files:
                print('No files in context')
            else:
                box_width = 42
                print('\n╔' + '═' * box_width + '╗')
                title = "ПРИКРЕПЛЕННЫЕ ФАЙЛЫ"
                print(f'║ {title:^{box_width-2}} ║')
                print('╠' + '─' * box_width + '╣')
                for idx, f in enumerate(files, 1):
                    line = f"{idx}. {f}"
                    if len(line) > box_width - 4:
                        line = line[:box_width-7] + "..."
                    print(f'║ {line:<{box_width-2}} ║')
                print('╚' + '═' * box_width + '╝\n')
            return True
            

        return False


class SessionCLIController:
    def __init__(self, agent: ChatAgent):
        self.agent = agent


    def print_help(self):
        print('\n╔════════════════════════════════════════╗')
        print('║             СПРАВКА ПО КОМАНДАМ        ║')
        print('╠════════════════════════════════════════╣')
        print('║ Глобальные команды:                    ║')
        print('║   /config   - Мастер конфигурации      ║')
        print('║   /models   - Статус моделей и фолбэков║')
        print('║   /prompt   - Редактировать системный  ║')
        print('║               промпт (SYSTEM_PROMPT.md)║')
        print('║                                        ║')
        print('║ Управление контекстом файлов:          ║')
        print('║   /add <путь>  - Добавить файл в чат   ║')
        print('║   /drop <путь> - Убрать файл из чата   ║')
        print('║   /files       - Список файлов в чате  ║')
        print('║                                        ║')
        print('║ Управление сессиями:                   ║')
        print('║   /sessions - Список сохранённых сессий║')
        print('║   /load <имя> - Загрузить сессию       ║')
        print('║   /save <имя> - Сохранить сессию       ║')
        print('║   /delete <имя> - Удалить сессию       ║')
        print('║                                        ║')
        print('║ Выход:                                 ║')
        print('║   exit / q  - Выход из программы       ║')
        print('╚════════════════════════════════════════╝\n')


    def prompt_session_selection(self):
        '''Интерактивное меню при старте программы (опциональный выбор/удаление сессий)'''

        sessions = self.agent.memory.list_sessions()
        if not sessions:
            return 
        
        print(f'Найдено сохраненных сессий: {len(sessions)}')
        print(f'Доступные сессии:')
        for idx, session in enumerate(sessions):
            print(f'{idx + 1}. {session}')
        choice = input('Введите номер сессии или нажмите Enter для создания новой: ').strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(sessions):
                selected_session = sessions[idx]
                try:
                    loaded_msgs = self.agent.memory.load_existing_session(selected_session)
                    self.agent.messages = loaded_msgs
                    print(f'Сессия {selected_session} загружена')
                except Exception as e:
                    print(f'Произошла ошибка при загрузке сессии: {e}')
        
            


    def handle_command(self, user_input: str) -> bool:
        '''Обрабатывает слэш-команды.
        Возвращает True, если команда была обработана, иначе False'''
        if not user_input.startswith('/'):
            return False
        parts = user_input.split(maxsplit=1)
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else None

        if cmd == '/help':
            self.print_help()
        elif cmd == '/sessions':
            all_sessions = self.agent.memory.list_sessions()
            if not all_sessions:
                print('Нет сохранённых сессий')
            else:
                print('Доступные сессии:')
                for sess in all_sessions:
                    print(f' - {sess}')
        elif cmd == '/load':
            if not arg:
                print('Пожалуйста, укажите имя сессии')
            else:
                try:
                    loaded_msgs = self.agent.memory.load_existing_session(arg)
                    self.agent.messages = loaded_msgs
                    print(f'Сессия {arg} загружена')
                except Exception as e:
                    print(f'Произошла ошибка при загрузке сессии: {e}')
        elif cmd == '/save':
            try:
                saved_name = self.agent.memory.save_dialogue_to_file(self.agent.messages, arg)
                print(f'Сессия сохранена как {saved_name}')
            except Exception as e:
                print(f'Произошла ошибка при сохранении сессии: {e}')
        elif cmd == '/delete':
            if not arg:
                print('Пожалуйста, укажите имя сессии')
            else:
                success =self.agent.memory.delete_session(arg)
                if success:
                    print(f'Сессия {arg} удалена')
                else:
                    print(f'Сессия {arg} не найдена')
        else:
            print('Неизвестная команда')
            return False

        return True


class CLIInputHandler:
    def __init__(self):
        self.session = PromptSession()


    def get_user_input(self) -> str:
        try:
            user_input = self.session.prompt(
                HTML('<b>Вы: </b>'),
                     multiline=False).strip()
            return user_input
        except (KeyboardInterrupt, EOFError):
            raise
        