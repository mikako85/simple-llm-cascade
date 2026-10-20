import json
import readline  # noqa: F401 — включает историю ввода в интерактивном CLI
import sys

import litellm
# litellm.set_verbose = True
from litellm import Router
from litellm.integrations.custom_logger import CustomLogger

from file_utils import ProjectContext

import config
from tools import (
    fetch_url_markdown,
    get_current_directory,
    get_system_time,
    list_directory,
    read_text_document,
    run_bash_command,
    search_web,
)
from memory_manager import MemoryManager
from schemas import TOOLS_SCHEMAS


# ИЗМЕНЕНО: per-deployment callback сообщает в CLI, какой fallback Router пробует.
# В LiteLLM callback вызывается на неудачной попытке deployment до следующего шага.
class _FallbackNoticeLogger(CustomLogger):
    def __init__(self, fallbacks_config: list):
        super().__init__()

        self.transition_map = {}
        for rule in fallbacks_config:
            primary = rule.primary
            chain = rule.chain
            full_chain = [primary] + chain
            for i in range(len(full_chain) - 1):
                self.transition_map[full_chain[i]] = full_chain[i + 1]


    async def async_post_call_failure_deployment_hook(
            self, request_data, exception, call_type, fallback_depth=None
    ):
        failed_route = None
        if isinstance(request_data, dict):
            model_name = request_data.get("model") or request_data.get("model_name")
            if not model_name and isinstance(request_data.get('litellm_params'), dict):
                model_name = request_data['litellm_params'].get('model_name')

            if model_name:
                failed_route = model_name

        next_route = self.transition_map.get(failed_route) if failed_route else None

        if not next_route and fallback_depth is not None:
            try:
                depth = int(fallback_depth)
                routes_sequence = list[self.transition_map.keys()]
                if routes_sequence and depth < len(routes_sequence):
                    failed_route = routes_sequence[depth]
                    next_route = self.transition_map.get(failed_route)
            except (ValueError, TypeError):
                pass

        if not next_route:
            return

        error_name = type(exception).__name__
        try:
            print(f'Trying fallback model: {next_route} for {error_name} in {failed_route}',
                  file=sys.stderr, flush=True)
        except Exception:
            return


def _register_fallback_notice_logger() -> None:
    """Добавляет уведомление в общие SDK callbacks, не удаляя чужие callbacks."""
    global _fallback_logger_instance

    if _fallback_logger_instance is None:
        _fallback_logger_instance = _FallbackNoticeLogger(config.app_config.fallbacks)

    callbacks = list[getattr(litellm, "callbacks", None) or []]

    if not any(isinstance(cb, _FallbackNoticeLogger) for cb in callbacks):
        callbacks.append(_fallback_logger_instance)

    litellm.callbacks = callbacks
    


class ChatAgent:
    def __init__(self, model_name: str | None = None):
        self.primary_model = model_name or config.ROUTER_PRIMARY_ROUTE

        fallback_logger = _FallbackNoticeLogger(config.app_config.fallbacks)

        callbacks = list(getattr(litellm, "callbacks", None) or [])
        if not any(isinstance(cb, _FallbackNoticeLogger) for cb in callbacks):
            callbacks.append(fallback_logger)
        litellm.callbacks = callbacks

        self.router = Router(
            model_list=config.build_router_model_list(),
            fallbacks=config.ROUTER_FALLBACKS,
            set_verbose=False,
            num_retries=0,
        )

        self.memory = MemoryManager()
        self.context = ProjectContext()
        global_memory = self.memory.load_global_memory()

        self.available_tools = {
            "get_current_directory": get_current_directory,
            "get_system_time": get_system_time,
            "read_text_document": read_text_document,
            "search_web": search_web,
            "run_bash_command": run_bash_command,
            "list_directory": list_directory,
            "fetch_url_markdown": fetch_url_markdown,
        }
        self.available_functions = self.available_tools

        self.messages = [
            {
                "role": "system",
                "content": (
                    "Ты полезный ассистент разработчика.\n\n"
                    "Долгосрочный контекст проекта (SYSTEM_PROMPT.md):\n"
                    f"{global_memory}"
                ),
            },
        ]

    def chat(self, user_input: str) -> None:
        self.messages.append({"role": "user", "content": user_input})
        current_iteration = 0

        

        while current_iteration < config.MAX_TOOL_ITERATIONS:
            current_iteration += 1

            messages_for_api = list(self.messages)  # ИЗМЕНЕНО: сохраняем исходные сообщения

            files_context = self.context.get_combined_context() if hasattr(self, 'context') else ''

            if files_context and messages_for_api:
                last_msg = messages_for_api[-1].copy()
                if last_msg['role'] == 'user':
                    last_msg['content'] = f'{files_context}\n\n User"s request: {user_input}'
                    messages_for_api[-1] = last_msg

            # ИЗМЕНЕНО: запрос идёт через Router. Fallback уже настроен при его создании;
            # здесь намеренно нет параметра fallbacks=.
            stream = self.router.completion(
                model=self.primary_model,
                messages=messages_for_api,
                tools=TOOLS_SCHEMAS,
                tool_choice="auto",
                temperature=config.TEMPERATURE,
                stream=True,
            )

            full_response = ""
            tool_calls_buffer: dict[int, dict[str, str]] = {}
            printed_response_prefix = False

            # ИЗМЕНЕНО: сохраняем потоковую выдачу, но берём только доступные поля чанка.
            # Это защищает от финальных служебных чанков без choices.
            for chunk in stream:
                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue

                delta = getattr(choices[0], "delta", None)
                if delta is None:
                    continue

                content = getattr(delta, "content", None)
                if isinstance(content, str) and content:
                    if not printed_response_prefix:
                        print("AI: ", end="", flush=True)
                        printed_response_prefix = True
                    print(content, end="", flush=True)
                    full_response += content

                delta_tool_calls = getattr(delta, "tool_calls", None)
                if not delta_tool_calls:
                    continue

                for tool_chunk in delta_tool_calls:
                    index = getattr(tool_chunk, "index", 0)
                    if index is None:
                        index = 0

                    if index not in tool_calls_buffer:
                        tool_calls_buffer[index] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }

                    tool_data = tool_calls_buffer[index]
                    call_id = getattr(tool_chunk, "id", None)
                    if call_id:
                        tool_data["id"] += call_id

                    function_delta = getattr(tool_chunk, "function", None)
                    if function_delta is not None:
                        function_name = getattr(function_delta, "name", None)
                        if function_name:
                            tool_data["name"] += function_name

                        arguments = getattr(function_delta, "arguments", None)
                        if isinstance(arguments, str):
                            tool_data["arguments"] += arguments

            if printed_response_prefix:
                print()

            if tool_calls_buffer:
                formatted_tool_calls = []
                for tool_data in tool_calls_buffer.values():
                    formatted_tool_calls.append(
                        {
                            "id": tool_data["id"],
                            "type": "function",
                            "function": {
                                "name": tool_data["name"],
                                "arguments": tool_data["arguments"],
                            },
                        }
                    )

                # Сохраняем вызов модели до результатов инструментов — так требует
                # OpenAI-совместимый формат истории диалога.
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": full_response or None,
                        "tool_calls": formatted_tool_calls,
                    }
                )

                for tool_call in formatted_tool_calls:
                    function_name = tool_call["function"]["name"]
                    raw_arguments = tool_call["function"]["arguments"]
                    tool_id = tool_call["id"]

                    try:
                        function_args = json.loads(raw_arguments) if raw_arguments else {}
                        if not isinstance(function_args, dict):
                            raise ValueError("Аргументы инструмента должны быть JSON-объектом")
                    except (json.JSONDecodeError, ValueError) as exc:
                        function_result = f"Некорректные аргументы инструмента: {exc}"
                    else:
                        print(
                            f"Вызываем функцию {function_name} "
                            f"с аргументами {function_args}"
                        )

                        if function_name not in self.available_functions:
                            function_result = f"Ошибка: функция {function_name} не найдена"
                        else:
                            target_function = self.available_functions[function_name]
                            try:
                                function_result = (
                                    target_function(**function_args)
                                    if function_args
                                    else target_function()
                                )
                            except Exception as exc:
                                function_result = (
                                    f"Ошибка при выполнении {function_name}: {exc}"
                                )

                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": str(function_result),
                        }
                    )

                # После ответа инструмента запрашиваем у Router следующий ход модели.
                continue

            self.messages.append(
                {"role": "assistant", "content": full_response}
            )
            return

        print(
            f"Достигнут предел итераций с инструментами "
            f"({config.MAX_TOOL_ITERATIONS})."
        )