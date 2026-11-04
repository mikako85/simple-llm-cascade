"""Entry point of the interactive agent CLI.

The module prepares the configuration, builds the chat agent and routes the
user input: global and session slash commands are handled by their
controllers, everything else is sent to the language model.
"""

from agent import ChatAgent
from app_paths import CONFIG_FILE
from cli_controller import (
    AppCLIController, CLIInputHandler, SessionCLIController, parse_cli_args)
from config_wizard import ConfigWizard



def main():
    """Start the interactive chat loop.

    The configuration wizard is launched first when models.yaml is missing.
    The loop ends on exit or q, or on Ctrl+C.

    Returns:
        None
    """
    ConfigWizard.ensure_config_exists(CONFIG_FILE)
    chosen_mode = parse_cli_args()
    agent = ChatAgent(mode=chosen_mode)
    app_controller = AppCLIController(agent)
    session_controller = SessionCLIController(agent)
    input_handler = CLIInputHandler()

    mode_display = agent.mode.value.upper()
    print(f'\n Chat opened with {agent.primary_model}. [Mode: {mode_display}] Type /help for help\n')
    session_controller.prompt_session_selection()

    while True:
        try:
            user_input = input_handler.get_user_input()
            if not user_input:
                continue

            if user_input.lower() in ['exit', 'q']:
                print('Session terminated')
                break

            if app_controller.handle_command(user_input):
                continue

            if session_controller.handle_command(user_input):
                continue

            agent.chat(user_input)
        except KeyboardInterrupt:
            print('Session terminated')
            break
        except Exception as e:
            print(f'An error occurred: {e}')


if __name__ == '__main__':
    main()
