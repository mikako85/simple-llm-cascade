"""Interactive configuration wizard for models.yaml and .env.

The wizard is started at boot when models.yaml is missing or empty, and
from the /config command at runtime. It lets the user add and remove model
routes, choose the default route and configure the fallback chains, then
writes the result back to the YAML file.
"""

import os
import sys

from pathlib import Path

import yaml

from dotenv import set_key


class ConfigWizard:
    """Interactive editor of the model configuration.

    Attributes:
        config_path: Path to the YAML configuration file.
        env_path: Path to the .env file holding the API keys.
        models: Model routes currently configured.
        default_route: Route used as the primary model.
        fallbacks: Fallback rules currently configured.
        settings: Global settings such as temperature and iteration limit.
    """

    def __init__(self, config_path: str = 'models.yaml', env_path: str = '.env'):
        """Load the existing configuration, if any.

        Args:
            config_path: Path to the YAML configuration file.
            env_path: Path to the .env file holding the API keys.
        """
        self.config_path = Path(config_path)
        self.env_path = Path(env_path)
        self.models: list[dict] = []
        self.default_route: str = ''
        self.fallbacks: list[dict] = []
        self.settings: dict = {
            'temperature': 0.7,
            'max_tool_iterations': 10,
            'keep_recent_tool_outputs': 3,
            'tool_stub_preserve_chars': 150
        }

        self.load_existing_config()


    def load_existing_config(self):
        """Read models.yaml into the wizard state.

        A missing, empty or malformed file leaves the default empty state,
        so the wizard can start from scratch.

        Returns:
            None
        """
        if self.config_path.exists() and self.config_path.stat().st_size > 0:
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                settings_block = data.get('settings')
                self.default_route = settings_block.get('default_route', '')

                for k, v in settings_block.items():
                    if k != 'default_route':
                        self.settings[k] = v

                self.models = data.get('models', [])
                self.fallbacks = data.get('fallbacks', [])
            except Exception as e:
                print(f'Error loading config: {e}')


    def _prompt_yes_no(self, question: str) -> bool:
        """Ask a yes/no question until a valid answer is given.

        Args:
            question: Question text shown to the user.

        Returns:
            True for yes, False for no.
        """
        while True:
            choice = input(f"{question} (y/n): ").strip().lower()
            if choice in ['y', 'yes']:
                return True
            elif choice in ['n', 'no']:
                return False
            print('Please, enter "y" or "n"')


    def add_model_flow(self):
        """Interactively add a new model route.

        The route name must be unique. The LiteLLM identifier has to use the
        provider/name form, and the API key environment variable name is
        derived from the provider unless the user overrides it.

        Returns:
            None
        """
        while True:
            model_name = input('Enter unique model name (for example groq-main): ').strip()
            if not model_name:
                print('Name cannot be empty')
                continue
            if any(m['model_name'] == model_name for m in self.models):
                print('Model with this name already exists')
                continue
            break

        while True:
            litellm_model = input('Enter LiteLLM model name (for example groq/llama-3.3-70b-versatile): ').strip()
            if '/' not in litellm_model:
                print('LiteLLM model name should contain "/", for example groq/llama-3.3-70b-versatile')
                continue
            break

        provider = litellm_model.split('/')[0].upper()
        default_env_var = f'{provider}_API_KEY'

        env_var_input = input(f'Environment variable for {litellm_model} (default: {default_env_var}): ').strip()
        api_key_env = env_var_input if env_var_input else default_env_var

        current_val = os.getenv(api_key_env)
        need_prompt = True

        if current_val:
            masked = current_val[:4] + '...' + current_val[-4:] if len(current_val) > 8 else '***'
            print(f'API key for {api_key_env} is already set in system environment({masked}).')
            override = input('Do you want to override it? (y/n): ').strip().lower()
            if override not in ['y', 'yes']:
                need_prompt = False

        if need_prompt:
            key_val = input(f'Enter API key for {api_key_env} (or press Enter to skip)').strip()
            if key_val:
                if not self.env_path.exists():
                    self.env_path.touch()

                set_key(str(self.env_path), api_key_env, key_val)
                os.environ[api_key_env] = key_val
                print(f'Saved {api_key_env} to {self.env_path}')
            else:
                print(f'Skipped key saving')
        
        self.models.append({
            'model_name': model_name,
            'litellm_model': litellm_model,
            'api_key_env': api_key_env
        })

        if not self.default_route:
            self.default_route = model_name

        print(f'Model {model_name} added successfully')


    def delete_model_flow(self):
        """Interactively delete a model route.

        The last remaining route cannot be deleted. When the default route is
        removed, the first remaining route becomes the new default, and the
        route is also removed from every fallback chain.

        Returns:
            None
        """
        print("\n--- delete model ---")

        if not self.models:
            print('No models to delete')
            input('Press Enter to continue...')
            return

        if len(self.models) <= 1:
            print('You cannot delete the last model')
            input('Press Enter to continue...')
            return

        print('Available models:')
        for idx, model in enumerate(self.models):
            marker = ' (by default)' if model['model_name'] == self.default_route else ''
            print(f'{idx + 1}. {model["model_name"]} [{model["litellm_model"]}]{marker}')

        choice = input('Enter the number of the model to delete: ').strip()
        if not choice.isdigit():
            print('Invalid choice')
            input('Press Enter to continue...')
            return

        idx = int(choice) - 1
        if not (0 <= idx < len(self.models)):
            print('Wrong model number')
            input('Press Enter to continue...')
            return

        target_model = self.models[idx]
        target_name = target_model['model_name']

        if not self._prompt_yes_no(f'Are you sure you want to delete model "{target_name}"?'):
            print('Deletion cancelled')
            return

        self.models.pop(idx)
        print(f'Model "{target_name}" deleted successfully')

        if self.default_route == target_name:
            self.default_route = self.models[0]['model_name']
            print(f'Default model changed to "{self.default_route}"')

        for fb in self.fallbacks:
            if fb.get('primary') == target_name:
                fb['primary'] = self.default_route
            if target_name in fb.get('chain', []):
                fb['chain'].remove(target_name)

        input('Press Enter to continue...')


    def configure_fallbacks_flow(self):
        """Interactively configure the fallback chains.

        The user can build a chain manually, generate a single standard
        chain from all models or clear the existing rules.

        Returns:
            None
        """
        while True:
            print('\n--- configure fallbacks ---')
            print('Current model by default (primary):', self.default_route or 'none')

            if self.fallbacks:
                print('Current fallbacks:')
                for idx, fb in enumerate(self.fallbacks):
                    print(f'{idx + 1}. primary: {fb.get("primary")} chain: {", ".join(fb.get("chain", []))}')
            else:
                print('No fallbacks configured')

            print('\n1. Add new fallback')
            print('2. Configure fallbacks automatically (from all models)')
            print('3. Clear all configured fallbacks')
            print('4. Back to main menu')

            choice = input('Enter your choice: ').strip()
            if choice == '1':
                if len(self.models) < 2:
                    print('You need at least 2 models to configure fallbacks')
                    input('Press Enter to continue...')
                    continue
                print('\nAvailable models:')
                for idx, model in enumerate(self.models):
                    print(f'{idx + 1}. {model["model_name"]}')

                primary_choice = input('Enter the number of the primary model: ').strip()
                if not primary_choice.isdigit():
                    print('Invalid choice')
                    input('Press Enter to continue...')
                    continue

                p_idx = int(primary_choice) - 1
                if not (0 <= p_idx < len(self.models)):
                    print('Wrong model number')
                    input('Press Enter to continue...')
                    continue

                primary_name = self.models[p_idx]['model_name']

                chain_list = []

                while True:
                    available_for_chain = [
                        m for m in self.models
                        if m['model_name'] != primary_name and m['model_name'] not in chain_list
                    ]

                    if not available_for_chain:
                        print('All models are already in the chain')
                        break

                    current = ", ".join(chain_list) if chain_list else "empty"
                    print(f'\n Current chain for model {primary_name}: {current}')
                    print('Choose a model to add to the chain or press Enter to finish:')

                    for idx, m in enumerate(available_for_chain):
                        print(f'{idx + 1}. {m["model_name"]}')

                    chain_choice = input('Enter the number of the model to add or press Enter to finish: ').strip()
                    if not chain_choice:
                        break

                    if not chain_choice.isdigit():
                        print('Invalid choice')
                        continue

                    c_idx = int(chain_choice) - 1
                    if 0 <= c_idx < len(available_for_chain):
                        chosen_fallback = available_for_chain[c_idx]['model_name']
                        chain_list.append(chosen_fallback)
                        print(f'Added {chosen_fallback} to the chain')
                    else:
                        print('Wrong model number')

                if chain_list:
                    existing_fb = next((fb for fb in self.fallbacks if fb.get('primary') == primary_name), None)
                    if existing_fb:
                        existing_fb['chain'] = chain_list
                    else:
                        self.fallbacks.append({'primary': primary_name, 'chain': chain_list})
                    print(f'Fallback for model {primary_name} configured successfully')
                else:
                    print(f'Fallback for model {primary_name} not configured')

                input('Press Enter to continue...')

            elif choice == '2':
                if len(self.models) < 2:
                    print('You need at least 2 models to configure fallbacks')
                else:
                    fallback_chain = [
                        m['model_name'] for m in self.models
                        if m['model_name'] != self.default_route
                    ]
                    if fallback_chain:
                        self.fallbacks = [{'primary': self.default_route, 'chain': fallback_chain}]
                        print('Standard chain configured successfully')
                    else:
                        print('Not enough models for a standard chain')

                input('Press Enter to continue...')

            elif choice == '3':
                if self.fallbacks:
                    if self._prompt_yes_no('Are you sure you want to clear all configured fallbacks?'):
                        self.fallbacks = []
                        print('Fallbacks cleared successfully')
                else:
                    print('No fallbacks to clear')

                input('Press Enter to continue...')

            elif choice == '4':
                break
            else:
                print('Invalid choice')
                input('Press Enter to continue...')


    def set_default_model_flow(self):
        """Interactively choose the active (default) model.

        Returns:
            None
        """

        print('\n--- SET DEFAULT MODEL ---')
        if not self.models:
            print('No models available')
            input('Press Enter to continue...')
            return

        print('Available models:')
        for idx, model in enumerate(self.models):
            marker = ' (current active)' if model['model_name'] == self.default_route else ''
            print(f'{idx + 1}. {model["model_name"]} [{model["litellm_model"]}]{marker}')

        choice = input('\nEnter the number of the model to set as default (or press Enter to skip): ').strip()
        if not choice.isdigit():
            print('Invalid choice')
            input('Press Enter to continue...')
            return

        idx = int(choice) - 1
        if 0 <= idx < len(self.models):
            self.default_route = self.models[idx]['model_name']
            print(f'Active model changed to "{self.default_route}" succesfully')
        else:
            print('Wrong model number')

        input('Press Enter to continue...')


    def save_config(self):
        """Write the current wizard state back to models.yaml.

        The default route is validated against the model list and replaced
        with the first model when it is missing.

        Returns:
            None
        """
        if not self.models:
            print('No models to save')
            return

        model_names = [m['model_name'] for m in self.models]
        if self.default_route not in model_names:
            self.default_route = self.models[0]['model_name']

        config_data = {
            'settings': {
                'default_route': self.default_route,
                'temperature': self.settings.get('temperature', 0.7),
                'max_tool_iterations': self.settings.get('max_tool_iterations', 10),
                'keep_recent_tool_outputs': self.settings.get('keep_recent_tool_outputs', 3),
                'tool_stub_preserve_chars': self.settings.get('tool_stub_preserve_chars', 150),
            },
            'models': self.models,
            'fallbacks': self.fallbacks,
        }

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f, sort_keys=False, allow_unicode=True)

        print(f'Config saved to {self.config_path}')


    def run(self):
        """Run the main wizard menu loop.

        Returns:
            None
        """
        while True:
            print('=== CONFIG WIZARD ===')
            print(f'Current model by default: {self.default_route or "not set"}')
            print(f'All models: {len(self.models)}')
            print('\n1. Add new model')
            print('2. Delete model')
            print('3. Set active (default) model')
            print('4. Set fallbacks / routes')
            print('5. Save changes and exit')
            print('6. Exit without saving')

            choice = input('Enter your choice: ').strip()
            if choice == '1':
                self.add_model_flow()
            elif choice == '2':
                self.delete_model_flow()
            elif choice == '3':
                self.set_default_model_flow()
            elif choice == '4':
                self.configure_fallbacks_flow()
            elif choice == '5':
                self.save_config()
                break
            elif choice == '6':
                print('Exiting without saving...')
                break
            else:
                print('Invalid choice. Please try again.')


    @classmethod
    def ensure_config_exists(cls, config_path: str = 'models.yaml'):
        """Create the configuration file when it is missing or empty.

        The wizard is started in that case, so the user can define at least
        one model route before the agent is constructed.

        Args:
            config_path: Path to the YAML configuration file.

        Returns:
            None
        """
        path = Path(config_path)
        if not path.exists() or path.stat().st_size == 0:
            print('Configuration file does not exist or is empty')
            print('Creating a new configuration file')

            wizard = cls(config_path=config_path)
            try:
                wizard.run()
            except KeyboardInterrupt:
                print('\nConfiguration cancelled')
            if not path.exists() or path.stat().st_size == 0:
                print('Configuration file was not created. Exiting.')
                sys.exit(1)
                


if __name__ == '__main__':
    wizard = ConfigWizard()
    wizard.run()
