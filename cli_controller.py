"""Command-line controllers for the interactive session.

The module separates three concerns:

* AppCLIController handles global commands such as /config and /models;
* SessionCLIController handles the dialog and session commands;
* CLIInputHandler reads user input through prompt_toolkit.
"""

import os
import argparse

import yaml
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML

from agent import ChatAgent
from app_paths import CONFIG_FILE
from config_wizard import ConfigWizard
from system_prompt_manager import _edit_system_prompt_interactive
from env_utils import is_firejail_available, is_wsl
from policy import ExecutionMode


class AppCLIController:
    """Handle application-level slash commands.

    Attributes:
        agent: Agent instance whose configuration and context are managed.
    """

    def __init__(self, agent: ChatAgent):
        """Store the agent the controller works with.

        Args:
            agent: Active chat agent.
        """
        self.agent = agent


    def show_models_status(self):
        """Print the models, the default route and the fallback chains.

        The data is read straight from models.yaml rather than from the
        running agent, so unsaved edits are not reflected here.

        Returns:
            None
        """
        config_path = CONFIG_FILE

        if not config_path.exists():
            print("❌ Configuration file models.yaml not found.")
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            print(f"❌ Failed to read the config: {e}")
            return

        settings = data.get("settings", {})
        models = data.get("models", [])
        fallbacks = data.get("fallbacks", [])
        default_route = settings.get("default_route", "Not set")

        box_width = 58  # Fixed width of the frame interior
        print('\n╔' + '═' * box_width + '╗')
        title = "MODEL AND FALLBACK STATUS"
        print(f'║ {title:^{box_width-2}} ║')
        print('╠' + '═' * box_width + '╣')

        route_str = f"⭐ Active route: {default_route}"
        print(f'║ {route_str:<{box_width-2}} ║')
        print('╠' + '─' * box_width + '╣')

        print(f'║ Models in the config:{"":<{box_width-2-21}} ║')
        for m in models:
            m_name = m.get("model_name", "unknown")
            litellm = m.get("litellm_model", "")
            marker = " (active)" if m_name == default_route else ""
            line1 = f"  • {m_name}{marker}"
            print(f'║ {line1:<{box_width-2}} ║')

            if litellm:
                # Truncate long LiteLLM identifiers to keep the frame aligned.
                if len(litellm) > box_width - 6:
                    litellm = litellm[:box_width-9] + "..."
                line2 = f"    ({litellm})"
                print(f'║ {line2:<{box_width-2}} ║')

        if fallbacks:
            print('╠' + '─' * box_width + '╣')
            print(f'║ Fallback chains:{"":<{box_width-2-16}} ║')
            for fb in fallbacks:
                primary = fb.get("primary", "")
                chain = ", ".join(fb.get("chain", []))
                line_fb = f"  {primary} ➔ [{chain}]"
                print(f'║ {line_fb:<{box_width-2}} ║')

        print('╚' + '═' * box_width + '╝\n')


    def handle_command(self, user_input: str) -> bool:
        """Handle application-level commands.

        Args:
            user_input: Raw line typed by the user.

        Returns:
            True when the input was a known command and has been handled,
            False when the input should be passed on.
        """
        cmd_stripped = user_input.strip()
      
        if cmd_stripped == '/config':
            wizard = ConfigWizard()
            wizard.run()
            self.agent.reload_router()
            print(f'Active model set to: {self.agent.primary_model}')
            return True

        if cmd_stripped == '/models':
            self.show_models_status()
            return True

        if cmd_stripped == '/prompt':
            _edit_system_prompt_interactive()
            return True


        if cmd_stripped.startswith('/add'):
            file_path = cmd_stripped[len('/add'):]
            if not file_path:
                print('Please specify the path to the file')
                return True
            try:
                self.agent.context.add(file_path)
                print(f'File {file_path} added to the context')
            except Exception as e:
                print(f'Error adding the file to the context: {e}')
            return True

        if cmd_stripped.startswith('/drop'):
            file_path = cmd_stripped[len('/drop'):]
            if not file_path:
                print('Please specify the path to the file')
                return True

            removed = self.agent.context.drop(file_path)
            if removed:
                print(f'File {file_path} removed from the context')
            else:
                print(f'File {file_path} not found in the context')
            return True

        if cmd_stripped.startswith('/files'):
            files = self.agent.context.get_files_list()
            if not files:
                print('No files in the context')
            else:
                box_width = 42
                print('\n╔' + '═' * box_width + '╗')
                title = "ATTACHED FILES"
                print(f'║ {title:^{box_width-2}} ║')
                print('╠' + '─' * box_width + '╣')
                for idx, f in enumerate(files, 1):
                    line = f"{idx}. {f}"
                    if len(line) > box_width - 4:
                        line = line[:box_width-7] + "..."
                    print(f'║ {line:<{box_width-2}} ║')
                print('╚' + '═' * box_width + '╝\n')
            return True

        # --- КОМАНДА /mode ---
        if cmd_stripped == '/mode' or cmd_stripped.startswith('/mode '):
            parts = cmd_stripped.split(maxsplit=1)
            if len(parts) == 1:
                current = self.agent.mode.value.upper()

                # Честное и точное определение статуса окружения
                if is_wsl():
                    env_status = "WSL environment (Firejail unsupported)"
                elif is_firejail_available():
                    env_status = "Native Linux (Firejail ready)"
                else:
                    env_status = "Linux (Firejail not installed)"

                print(f"\n⚙️  Current execution mode: \033[1;36m{current}\033[0m ({env_status})")
                print("Available modes to switch: /mode ask, /mode yolo, /mode sandbox\n")
                return True

            target_mode_str = parts[1].strip().lower()
            if target_mode_str not in {'ask', 'yolo', 'sandbox'}:
                print("❌ Unknown mode. Choose from: 'ask', 'yolo', 'sandbox'")
                return True

            target_mode = ExecutionMode(target_mode_str)

            # Точная и информативная диагностика при попытке включить sandbox
            if target_mode == ExecutionMode.SANDBOX:
                if is_wsl():
                    print("❌ Cannot switch to 'sandbox': Firejail is not supported inside WSL.")
                    print("   Please use 'ask' or 'yolo' modes.")
                    return True
                elif not is_firejail_available():
                    print("❌ Cannot switch to 'sandbox': Firejail is not installed on this system.")
                    print("   Install it via your package manager (e.g. 'sudo apt install firejail') or use 'ask'/'yolo'.")
                    return True

            # Переключаем режим агента на лету
            self.agent.set_mode(target_mode)
            print(f"✅ Execution mode successfully changed to: \033[1;32m{target_mode.value.upper()}\033[0m")
            return True


        return False


class SessionCLIController:
    """Handle dialogue and session slash commands.

    Attributes:
        agent: Agent whose history and memory are managed.
    """

    def __init__(self, agent: ChatAgent):
        """Store the agent the controller works with.

        Args:
            agent: Active chat agent.
        """
        self.agent = agent


    def print_help(self):
        """Print the list of available commands.

        Returns:
            None
        """
        print('\n╔════════════════════════════════════════╗')
        print('║            COMMAND REFERENCE           ║')
        print('╠════════════════════════════════════════╣')
        print('║ Global commands:                       ║')
        print('║   /mode [name] - View or switch mode   ║')
        print('║                  (ask / yolo / sandbox)║')
        print('║   /config   - Configuration wizard     ║')
        print('║   /models   - Models and fallbacks     ║')
        print('║   /prompt   - Edit the system prompt   ║')
        print('║               (SYSTEM_PROMPT.md)       ║')
        print('║                                        ║')
        print('║ File context:                          ║')
        print('║   /add <path>  - Attach a file         ║')
        print('║   /drop <path> - Detach a file         ║')
        print('║   /files       - List attached files   ║')
        print('║                                        ║')
        print('║ Session management:                    ║')
        print('║   /sessions - List saved sessions      ║')
        print('║   /load <name> - Load a session        ║')
        print('║   /save <name> - Save a session        ║')
        print('║   /delete <name> - Delete a session    ║')
        print('║                                        ║')
        print('║ Exit:                                  ║')
        print('║   exit / q  - Quit the program         ║')
        print('╚════════════════════════════════════════╝\n')


    def prompt_session_selection(self):
        """Let the user pick a saved session at start-up.

        The list of sessions is printed and the user may enter a number to
        restore that history. Pressing Enter creates a new session.

        Returns:
            None
        """
        sessions = self.agent.memory.list_sessions()
        if not sessions:
            return

        print(f'Saved sessions found: {len(sessions)}')
        print('Available sessions:')
        for idx, session in enumerate(sessions):
            print(f'{idx + 1}. {session}')
        choice = input('Enter the session number or press Enter to create a new one: ').strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(sessions):
                selected_session = sessions[idx]
                try:
                    loaded_msgs = self.agent.memory.load_existing_session(selected_session)
                    self.agent.messages = loaded_msgs
                    print(f'Session {selected_session} loaded')
                except Exception as e:
                    print(f'Failed to load the session: {e}')


    def handle_command(self, user_input: str) -> bool:
        """Handle session and dialogue commands.

        Args:
            user_input: Raw line typed by the user.

        Returns:
            True when the command was recognised, False otherwise.
        """
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
                print('No saved sessions')
            else:
                print('Available sessions:')
                for sess in all_sessions:
                    print(f' - {sess}')
        elif cmd == '/load':
            if not arg:
                print('Please specify the session name')
            else:
                try:
                    loaded_msgs = self.agent.memory.load_existing_session(arg)
                    self.agent.messages = loaded_msgs
                    print(f'Session {arg} loaded')
                except Exception as e:
                    print(f'Failed to load the session: {e}')
        elif cmd == '/save':
            try:
                saved_name = self.agent.memory.save_dialogue_to_file(self.agent.messages, arg)
                print(f'Session saved as {saved_name}')
            except Exception as e:
                print(f'Failed to save the session: {e}')
        elif cmd == '/delete':
            if not arg:
                print('Please specify the session name')
            else:
                success = self.agent.memory.delete_session(arg)
                if success:
                    print(f'Session {arg} deleted')
                else:
                    print(f'Session {arg} not found')
        else:
            print('Unknown command')
            return False

        return True


class CLIInputHandler:
    """Read user input through prompt_toolkit.

    Attributes:
        session: PromptSession instance holding the input state.
    """

    def __init__(self):
        """Create the prompt session."""
        self.session = PromptSession()


    def get_user_input(self) -> str:
        """Read one line of user input.

        Returns:
            Trimmed input line.

        Raises:
            KeyboardInterrupt: When the user presses Ctrl+C.
            EOFError: When the input stream is closed (Ctrl+D).
        """
        try:
            user_input = self.session.prompt(
                HTML('<b>You: </b>'),
                multiline=False).strip()
            return user_input
        except (KeyboardInterrupt, EOFError):
            raise


def parse_cli_args() -> str | None:
    """Parse command line flags for execution mode overrides
    
    Returns: 
        str | None: Seelcted mode name or None if relying on models.yaml
    """

    parser = argparse.ArgumentParser(
        description='Simple LLM Cascade - Interactive AI Developer Assistant'
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--mode',
        '-m',
        choices=['ask', 'yolo', 'sandbox'],
        help='Explicitly set the execution mode ("ask", "yolo" or "sandbox")'
    )
    mode_group.add_argument(
        '--yolo',
        '-y',
        action='store_true',
        help='Run in autonomous YOLO mode (no confirmation for writes/bash)'
    )
    mode_group.add_argument(
        '--ask',
        '-a',
        action='store_true',
        help='Run in interactive ask mode (confirmation for writes/bash)'
    )
    mode_group.add_argument(
        '--sandbox',
        '-s',
        action='store_true',
        help='Run in sandbox mode (Firejail, native Linux only)'
    )

    args = parser.parse_args()
    if args.yolo:
        return 'yolo'
    elif args.ask:
        return 'ask'
    elif args.sandbox:
        return 'sandbox'
    elif args.mode:
        return args.mode
    else:
        return None
    
