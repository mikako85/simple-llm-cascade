import os
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

API_KEY = OPENROUTER_API_KEY

PRIMARY_MODEL = 'groq/openai/gpt-oss-120b'
OPENROUTER_FALLBACK_MODEL = 'openrouter/nvidia/nemotron-3-super-120b-a12b:free'
DEEPSEEK_FALLBACK_MODEL = 'deepseek/deepseek-flash'

ROUTER_PRIMARY_ROUTE = 'groq-primary'
ROUTER_OPENROUTER_ROUTE = 'openrouter-fallback'
ROUTER_DEEPSEEK_ROUTE = 'deepseek-fallback'

ROUTER_FALLBACKS = [
    {
        ROUTER_PRIMARY_ROUTE: [
            ROUTER_OPENROUTER_ROUTE,
            ROUTER_DEEPSEEK_ROUTE
        ]
    }
]

TEMPERATURE = 0.7
MAX_TOOL_ITERATIONS = 10


def build_router_model_list() -> list[dict]:
    missing_keys = []
    if not GROQ_API_KEY:
        missing_keys.append('GROQ_API_KEY')
    if not OPENROUTER_API_KEY:
        missing_keys.append('OPENROUTER_API_KEY')
    if not DEEPSEEK_API_KEY:
        missing_keys.append('DEEPSEEK_API_KEY')
    if missing_keys:
        missing = ', '.join(missing_keys)
        raise RuntimeError(f"Missing API keys: {missing}")

    return [
        {
            'model_name': ROUTER_PRIMARY_ROUTE,
            'litellm_params': {
                'model': PRIMARY_MODEL,
                'api_key': GROQ_API_KEY
            },

        },
        {
            'model_name': ROUTER_OPENROUTER_ROUTE,
            'litellm_params': {
                'model': OPENROUTER_FALLBACK_MODEL,
                'api_key': OPENROUTER_API_KEY
            }
        },
        {
            'model_name': ROUTER_DEEPSEEK_ROUTE,
            'litellm_params': {
                'model': DEEPSEEK_FALLBACK_MODEL,
                'api_key': DEEPSEEK_API_KEY
            }
        }
    ]