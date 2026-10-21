"""Validation and loading of the models.yaml configuration.

The YAML file describes the available model routes, the default route and
the fallback chains. Pydantic models validate the structure at start-up, so
a malformed config fails early with a readable message instead of breaking
the first request.
"""

from pathlib import Path

import yaml

from pydantic import BaseModel, Field, field_validator

from config_wizard import ConfigWizard


class SettingsConfig(BaseModel):
    """Global agent settings.

    Attributes:
        default_route: Route used as the primary model.
        temperature: Sampling temperature between 0 and 1.
        max_tool_iterations: Upper bound of tool-calling rounds per request.
    """

    default_route: str = Field(..., description='logic route by default')
    temperature: float = Field(0.7, ge=0.0, le=1.0, description='temperature of generation')
    max_tool_iterations: int = Field(10, ge=0, description='max tool iterations')


class ModelRouteConfig(BaseModel):
    """Description of a single model deployment.

    Attributes:
        model_name: Internal route name used in the config and by the Router.
        litellm_model: LiteLLM identifier, for example groq/llama-3.3-70b.
        api_key_env: Name of the environment variable that holds the key.
    """

    model_name: str = Field(..., description='model name')
    litellm_model: str = Field(..., description='litellm model')
    api_key_env: str = Field(..., description='litellm api key env')


class FallbackRuleConfig(BaseModel):
    """Fallback chain attached to a primary route.

    Attributes:
        primary: Route that is tried first.
        chain: Routes tried in order when the primary one fails.
    """

    primary: str = Field(..., description='primary route')
    chain: list[str] = Field(..., description='fallback routes')


class AppConfig(BaseModel):
    """Top-level structure of models.yaml.

    Attributes:
        settings: Global agent settings.
        models: Non-empty list of model deployments.
        fallbacks: Fallback chains; an empty list disables fallback.
    """

    settings: SettingsConfig
    models: list[ModelRouteConfig] = Field(..., min_length=1, description='list of models')
    fallbacks: list[FallbackRuleConfig] = Field(default_factory=list)


    @field_validator('models')
    @classmethod
    def validate_unique_models(cls, v: list[ModelRouteConfig]) -> list[ModelRouteConfig]:
        """Ensure every model name appears only once.

        Args:
            v: Parsed list of model deployments.

        Returns:
            The unchanged list when all names are unique.

        Raises:
            ValueError: If duplicate model names are present.
        """
        names = [m.model_name for m in v]
        if len(names) != len(set(names)):
            raise ValueError('Model names must be unique')
        return v


def load_config(config_path: str | Path = 'models.yaml') -> AppConfig:
    """Load and validate the YAML configuration.

    When the file is missing or empty the interactive configuration wizard
    is started to create it.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Validated application configuration.

    Raises:
        ValueError: If the file stays empty after the wizard has run.
    """
    path = Path(config_path)
    if not path.exists() or path.stat().st_size == 0:
        print('Configuration file does not exist or is empty')
        ConfigWizard.ensure_config_exists(config_path)

    with open(path, 'r', encoding='utf-8') as f:
        raw_data = yaml.safe_load(f)

    if not raw_data:
        raise ValueError('Config file is empty')

    return AppConfig(**raw_data)
