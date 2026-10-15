from agent import ChatAgent
import config
from cli_controller import SessionCLIController, CLIInputHandler




def main():
    agent = ChatAgent()
    controller = SessionCLIController(agent)
    input_handler = CLIInputHandler()

    controller.interactive_startup()

    print(f'\n Открыт чат с {config.PRIMARY_MODEL}. введите /help для помощи\n')
    


    while True:
        try:
            user_input = input_handler.get_user_input()
            if not user_input:
                continue
                    
            if user_input.lower() in ['exit', 'q']:
                print('Завершение сеанса')
                break
            if controller.handle_command(user_input):
                continue

            agent.chat(user_input)
        except KeyboardInterrupt:
            print('Завершение сеанса')
            break
        except Exception as e:
            print(f'Произошла ошибка: {e}')


if __name__ == '__main__':
    main()