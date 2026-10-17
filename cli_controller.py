import os
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from agent import ChatAgent
import config


class SessionCLIController:
    def __init__(self, agent: ChatAgent):
        self.agent = agent


    def print_help(self):
        print('\n=== КОМАНДЫ УПРАВЛЕНИЯ СЕССИЯМИ ===')
        print(' /sessions - список сохранённых сессий')
        print(' /load <имя> - загрузить сессию')
        print(' /save <имя> - сохранить сессию')
        print(' /delete <имя> - удалить сессию')
        print(' exit /q - выход из программы')
        print('=== КОМАНДЫ УПРАВЛЕНИЯ СЕССИЯМИ ===\n')


    def interactive_startup(self):
        '''Интерактивное меню при старте программы (опциональный выбор/удаление сессий)'''

        available_models = config.app_config.models
        default_route = config.app_config.settings.default_route

        print('\n=== ВЫБОР МОДЕЛИ (МАРШРУТА) ===')
        print(f'По умолчанию: {default_route}')
        for idx, m in enumerate(available_models):
            marker = ' (по умолчанию)' if m.model_name == default_route else ''
            print(f'{idx + 1}. {m.model_name} [{m.litellm_model}]{marker}')

        model_choice = input('Choice model"s number or Enter for default: ').strip()
        if model_choice.isdigit():
            idx = int(model_choice) - 1
            if 0 <= idx < len(available_models):
                selected_model_name = available_models[idx].model_name
                self.agent.primary_model = selected_model_name
                print(f'Выбрана модель: {selected_model_name}')

        self.print_help()
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
        