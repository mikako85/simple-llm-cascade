"""Runtime configuration derived from .env and models.yaml.

The module loads the environment variables, validates models.yaml and
exposes ready-to-use values for the rest of the application: the sampling
temperature, the tool-iteration limit, the primary route and the fallback
chains of the LiteLLM router.
"""

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

KEEP_RECENT_TOOL_OUTPUTS = app_config.settings.keep_recent_tool_outputs
TOOL_STUBS = app_config.settings.tool_stub_preserve_chars

ROUTER_PRIMARY_ROUTE = app_config.settings.default_route

EXECUTION_MODE = app_config.settings.execution_mode

ROUTER_FALLBACKS = [
    {rule.primary: rule.chain} for rule in app_config.fallbacks
]


def build_router_model_list() -> list[dict]:
    """Build the model_list argument of the LiteLLM Router.

    Every configured model is turned into a Router deployment, with the API
    key resolved from the environment variable named in the config.

    Returns:
        List of Router deployment descriptions.

    Raises:
        RuntimeError: If an API key environment variable is missing.
    """
    missing_keys = []
    router_models = []

    for model_cfg in app_config.models:
        api_key = os.getenv(model_cfg.api_key_env)
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
