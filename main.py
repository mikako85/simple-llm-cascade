from agent import ChatAgent
import config
from cli_controller import SessionCLIController, CLIInputHandler, AppCLIController
from config_wizard import ConfigWizard




def main():
    ConfigWizard.ensure_config_exists()
    agent = ChatAgent()
    app_controller = AppCLIController()
    session_controller = SessionCLIController(agent)
    input_handler = CLIInputHandler()

    
    session_controller.interactive_startup()

    print(f'\n Открыт чат с {agent.primary_model}. введите /help для помощи\n')
    
    while True:
        try:
            user_input = input_handler.get_user_input()
            if not user_input:
                continue
                    
            if user_input.lower() in ['exit', 'q']:
                print('Завершение сеанса')
                break

            if app_controller.handle_command(user_input):
                continue

            if session_controller.handle_command(user_input):
                continue

            agent.chat(user_input)
        except KeyboardInterrupt:
            print('Завершение сеанса')
            break
        except Exception as e:
            print(f'Произошла ошибка: {e}')


if __name__ == '__main__':
    main()