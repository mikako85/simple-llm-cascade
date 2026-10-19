import os
import yaml
from pathlib import Path


class ConfigWizard:
    def __init__(self, config_path: str  = 'models.yaml', env_path: str = '.env'):
        self.config_path = Path(config_path)
        self.env_path = Path(env_path)
        self.models: list[dict] = []
        self.default_route: str = ''
        self.fallbacks: list[dict] = []
        self.settings: dict = {
            'temperature': 0.7,
            'max_tool_iterations': 10
        }

        self.load_existing_config()


    def load_existing_config(self):
        '''load existing config'''
        if self.config_path.exists() and self.config_path.stat().st_size > 0:
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
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
        while True:
            choice = input(f"{question} (y/n): ").strip().lower()
            if choice in ['y', 'yes']:
                return True
            elif choice in ['n', 'no']:
                return False
            print('Please, enter "y" or "n"')


    def add_model_flow(self):
        '''interactive steps for adding new model'''
        while True:
            model_name = input('Enter unigue model name(for example groq-main): ').strip()
            if not model_name:
                print('name can not be empty')
                continue
            if any(m['model_name'] == model_name for m in self.models):
                print('Model with this name already exists')
                continue
            break

        while True:
            litellm_model = input('Enter litellm model name(for example groq/llama-3.3-70b-versatile): ').strip()
            if '/' not in litellm_model:
                print('litellm model name should contain "/" for example "groq/llama-3.3-70b-versatile"')
                continue
            break

        provider = litellm_model.split('/')[0].upper()
        default_env_var = f'{provider}_API_KEY'

        env_var_input = input(f'Environment variable for {litellm_model} (default: {default_env_var}): ').strip()
        api_key_env = env_var_input if env_var_input else default_env_var

        self.models.append({
            'model_name': model_name,
            'litellm_model': litellm_model,
            'api_key_env': api_key_env
        })
        print('Model added successfully')

        if not self.default_route:
            self.default_route = model_name

        print(f'Model: {model_name} successfully added')


    def delete_model_flow(self):
        '''interactive steps for deleting model'''
        print("\n---delete model---")

        if not self.models:
            print('No models to delete')
            input('Press Enter to continue...')
            return

        if len(self.models) <= 1:
            print('You can not delete last model')
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
            print('wrong model"s number')
            input('Press Enter to continue...')
            return

        target_model = self.models[idx]
        target_name = target_model['model_name']

        if not self._prompt_yes_no(f'Are you sure you want to delete model "{target_name}"?'):
            print('Deletion canceled')
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
        '''interactive steps for configuring fallbacks'''
        while True:
            print('\n---configure fallbacks---')
            print('Current model by default (primary):', self.default_route or 'none')

            if self.fallbacks:
                print('Current fallbacks:')
                for idx, fb in enumerate(self.fallbacks):
                    print(f'{idx + 1}. main: {fb.get("primary")} chain: {", ".join(fb.get("chain", []))}')
            else:
                print('No fallbacks configured')

            print('\n1 Add new fallback')
            print('2. Automatically configure fallbacks (from all models)')
            print('3. Clean all configured fallbacks')
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
                    print('wrong model"s number')
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

                    print(f'\n Current chain for model {primary_name}: {", ".join(chain_list if chain_list else "empty")}')
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
                    if (0 <= c_idx < len(available_for_chain)):
                        chosen_fallback = available_for_chain[c_idx]['model_name']
                        chain_list.append(chosen_fallback)
                        print(f'Added {chosen_fallback} to the chain')
                    else:
                        print('wrong model"s number')

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
                    fallback_chain = [m['model_name'] for m in self.models if m['model_name'] != self.default_route]
                    if fallback_chain:
                        self.fallbacks = [{'primary': self.default_route, 'chain': fallback_chain}]
                        print('Standard chain configured successfully')
                    else:
                        print('Not enough models for standard chain')

                input('Press Enter to continue...')

            elif choice == '3':
                if self.fallbacks:
                    if self._prompt_yes_no('Are you sure you want to clean all configured fallbacks?'):
                        self.fallbacks = []
                        print('Fallbacks cleaned successfully')
                else:
                    print('No fallbacks to clean')

                input('Press Enter to continue...')

            elif choice == '4':
                break
            else:
                print('Invalid choice')
                input('Press Enter to continue...')

    def save_config(self):
        '''save config to yaml file'''
        if not self.models:
            print('No models for saving')
            return

        model_names = [m['model_name'] for m in self.models]
        if self.default_route not in model_names:
            self.default_route = self.models[0]['model_name']

        config_data = {
            'settings': {
                'default_route': self.default_route,
                'temperature': self.settings.get('temperature', 0.7),
                'max_tool_iterations': self.settings.get('max_tool_iterations', 10)
            },
                'models': self.models,
                'fallbacks': self.fallbacks

        }

        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config_data, f, sort_keys=False, allow_unicode=True)

        print(f'Config saved to {self.config_path}')


    def run(self):
        '''main method for running config wizard'''
        while True:
            print('=== CONFIG WIZARD ===')
            print(f'Current model by default: {self.default_route or "not set"}')
            print(f'All models: {len(self.models)}')
            print('\n1. Add new model')
            print('2. Delete model')
            print('3. Set fallbacks / routes')
            print('4. Save changes and exit')
            print('5. Exit without saving')

            choice = input('Enter your choice: ').strip()
            if choice == '1':
                self.add_model_flow()
            elif choice == '2':
                self.delete_model_flow()
            elif choice == '3':
                self.configure_fallbacks_flow()
            elif choice == '4':
                self.save_config()
                break
            elif choice == '5':
                print('Exiting without saving...')
                break
            else:
                print('Invalid choice. Please try again.')
            



    @classmethod
    def ensure_config_exists(cls, config_path: str = 'models.yaml'):
        '''create config file if not exists'''
        path = Path(config_path)
        if not path.exists() or path.stat().st_size == 0:
            print('configuration"s file don"t exist or empty')
            print('creating new configuration"s file')

            wizard = cls(config_path=config_path)
            wizard.run()
        else:
            print('configuration"s file already exists')
        
            



if __name__ == '__main__':
    wizard = ConfigWizard()
    wizard.run()
            
        

            