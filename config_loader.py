from pathlib import Path
import yaml
from pydantic import BaseModel, Field, field_validator
from config_wizard import ConfigWizard


class SettingsConfig(BaseModel):
    default_route: str = Field(..., description='logic route by default')
    temperature: float = Field(0.7, ge=0.0, le=1.0, description='temperature of generation')
    max_tool_iterations: int = Field(10, ge=0, description='max tool iterations')


class ModelRouteConfig(BaseModel):
    model_name: str = Field(..., description='model name')
    litellm_model: str = Field(..., description='litellm model')
    api_key_env: str = Field(..., description='litellm api key env')


class FallbackRuleConfig(BaseModel):
    primary: str = Field(..., description='primary route')
    chain: list[str] = Field(..., description='fallback routes')


class AppConfig(BaseModel):
    settings: SettingsConfig
    models: list[ModelRouteConfig] = Field(..., min_length=1, description='list of models')
    fallbacks: list[FallbackRuleConfig] = Field(default_factory=list)


    @field_validator('models')
    @classmethod
    def validate_unique_models(cls, v: list[ModelRouteConfig]) -> list[ModelRouteConfig]:
        names = [m.model_name for m in v]
        if len(names) != len(set(names)):
            raise ValueError('Model names must be unique')
        return v


def load_config(config_path: str | Path = 'models.yaml') -> AppConfig:
    path = Path(config_path)
    if not path.exists() or path.stat().st_size == 0:
        print('Configuration"s file don"t exist or empty')
        ConfigWizard.ensure_config_exists(config_path)

    with open(path, 'r', encoding='utf-8') as f:
        raw_data = yaml.safe_load(f)

    if not raw_data:
        raise ValueError('Config file is empty')

    return AppConfig(**raw_data)
    

    