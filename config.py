import os
from dotenv import load_dotenv
from config_loader import AppConfig, load_config

load_dotenv()

try:
    app_config: AppConfig = load_config('models.yaml')
except (FileNotFoundError, ValueError) as e:
    print(f"Error loading config: {e}. Need to create models.yaml file")
    raise

TEMPERATURE = app_config.settings.temperature
MAX_TOOL_ITERATIONS = app_config.settings.max_tool_iterations

ROUTER_PRIMARY_ROUTE = app_config.settings.default_route

ROUTER_FALLBACKS = [
    {rule.primary: rule.chain} for rule in app_config.fallbacks
]
def build_router_model_list() -> list[dict]:
    missing_keys = []
    router_models = []

    for model_cfg in app_config.models:
        api_key = os.getenv(model_cfg.api_key_env)
        # print(f"[DEBUG CONFIG] Model: {model_cfg.model_name} | Env var: {model_cfg.api_key_env} | Key loaded?: {bool(api_key)} (len: {len(api_key) if api_key else 0})")
        if not api_key:
            missing_keys.append(model_cfg.api_key_env)
        router_models.append(
            {
                'model_name': model_cfg.model_name,
                'litellm_params': {
                    'model': model_cfg.litellm_model,
                    'api_key': api_key,
                },
            }
        )

    if missing_keys:
        unique_missing = ', '.join(sorted(set(missing_keys)))
        raise RuntimeError(
            f"Missing environment variables for models: {unique_missing}"
        )

    return router_models