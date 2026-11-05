"""Chat agent built on top of the LiteLLM Router.

The module wires together the model router with fallback chains, the tool
set, the long-term memory and the attached project files. A single chat turn
may involve several model calls when the model requests tools, so the agent
loops until it produces a final answer or the iteration limit is reached.
"""

import json
import readline  # noqa: F401 - enables input history in the interactive CLI
import sys

import litellm
from litellm import Router
from litellm.integrations.custom_logger import CustomLogger

import config
from context_utils import prune_tool_message
from file_utils import ProjectContext
from memory_manager import MemoryManager
from schemas import TOOLS_SCHEMAS
from tools import (
    fetch_url_markdown,
    get_current_directory,
    get_system_time,
    list_directory,
    read_text_document,
    write_file,
    run_bash_command,
    search_web,
    set_execution_mode
)
from env_utils import is_firejail_available
from policy import ExecutionMode, ToolInterceptor
from tools import set_execution_mode

import logging

# Disable debug information and suppress LiteLLM warnings
litellm.suppress_debug_info = True
litellm.suppress_warnings = True
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logging.getLogger("LiteLLM Router").setLevel(logging.ERROR)

class _FallbackNoticeLogger(CustomLogger):
    """Report Router fallback transitions to stderr.

    LiteLLM calls this hook for every failed deployment, before trying the
    next route in the chain, which makes it a convenient place to tell the
    user that a fallback model is being tried.

    Attributes:
        transition_map: Mapping of each route to the route tried after it.
    """

    def __init__(self, fallbacks_config: list):
        """Build the route transition map from the fallback rules.

        Args:
            fallbacks_config: Fallback rules, each with a primary route and
                a chain of alternative routes.
        """
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
        """Announce the next route in the chain after a failed deployment.

        The failed route is taken from request_data when possible and
        otherwise derived from fallback_depth.

        Args:
            request_data: Request payload of the failed call.
            exception: Exception raised by the deployment.
            call_type: LiteLLM call type (completion, embedding, ...).
            fallback_depth: Zero-based index of the failed attempt.

        Returns:
            None
        """
        failed_route = None
        if isinstance(request_data, dict):
            model_name = request_data.get("model") or request_data.get("model_name")
            if not model_name and isinstance(request_data.get("litellm_params"), dict):
                model_name = request_data['litellm_params'].get('model_name')

            if model_name:
                failed_route = model_name

        next_route = self.transition_map.get(failed_route) if failed_route else None

        if not next_route and fallback_depth is not None:
            try:
                depth = int(fallback_depth)
                routes_sequence = list(self.transition_map.keys())
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


class ChatAgent:
    """Stateful chat agent with tools, memory and model fallback.

    The agent owns the LiteLLM Router, the message history, the tool table
    and the attached file context. One instance corresponds to one CLI
    session.

    """

    def __init__(self, model_name: str | None = None, mode: ExecutionMode | str | None = None):
        """Create the router, register the fallback logger, load memory and security police.

        Args:
            model_name: Primary route to use. Defaults to the route from
                models.yaml.
        """
        self.primary_model = model_name or config.ROUTER_PRIMARY_ROUTE

        requested_mode = ExecutionMode.from_string(mode or getattr(config, 'EXECUTION_MODE', 'ask'))
        if requested_mode == ExecutionMode.SANDBOX and not is_firejail_available():
            print(
                "\n\033[1;33m  WARNING: Sandbox mode (Firejail) is unavailable in this environment (WSL). "
                "Automatically switched to 'ask' mode.\033[0m\n",
                file=sys.stderr,
                flush=True
            )
            self.mode = ExecutionMode.ASK
        else:
            self.mode = requested_mode

        set_execution_mode(self.mode)
        self.interceptor = ToolInterceptor(default_mode=self.mode)

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
            "write_file": write_file,
            "search_web": search_web,
            "run_bash_command": run_bash_command,
            "list_directory": list_directory,
            "fetch_url_markdown": fetch_url_markdown,
        }
        self.available_functions = self.available_tools

        self.messages = [
            {
                "role": "system",
                "content": self.build_system_prompt()
            },
        ]


    def build_system_prompt(self) -> str:
        """Construct a comprehensive system prompt reflecting the active mode and tools."""
        global_memory = self.memory.load_global_memory()
        mode_desc = {
            ExecutionMode.SANDBOX: 'SANDBOX (bash runs in isolated Firejail, file operations locked to workspace)',
            ExecutionMode.ASK: 'ASK (runs on host; file mofifications and bash commands require interactive user approval)',
            ExecutionMode.YOLO: 'YOLO (runs autonomously on host without confirmation prompts '
        }.get(self.mode, 'Standard')

        return (
            "You are an expert autonomous developer assistant operating directly in the environment.\n\n"
            f"### ACTIVE EXECUTION MODE: {mode_desc}\n\n"
            "### AVAILABLE TOOLS & CAPABILITIES:\n"
            "- write_file: Creates a new file or completely overwrites an existing file. "
            "ALWAYS use this tool to write, edit, or create files. Do NOT use bash echo/cat.\n"
            "- read_text_document: Inspect file contents.\n"
            "- list_directory: List files and folders.\n"
            "- run_bash_command: Execute bash commands, git, builds, and tools.\n"
            "- search_web & fetch_url_markdown: Research online docs and articles.\n"
            "- get_current_directory & get_system_time: Inspect runtime state.\n\n"
            "### RULES OF ENGAGEMENT:\n"
            "1. When asked to create, refactor, or write code to a file, invoke the `write_file` tool.\n"
            "2. In Sandbox mode, file paths are confined to the workspace. In Ask/YOLO modes, host paths (Desktop, home folder, etc.) are accessible.\n"
            "3. Answer user questions directly after calling appropriate tools.\n\n"
            "### LONG-TERM PROJECT CONTEXT (SYSTEM_PROMPT.md):\n"
        )


    def set_mode(self, new_mode: ExecutionMode) -> None:
        """Dynamically change execution mode and synchronize tools."""
        self.mode = new_mode
        self.interceptor.set_mode(new_mode)
        set_execution_mode(new_mode)

        if self.messages and self.messages[0].get('role') == 'system':
            self.messages[0]['content'] = self.build_system_prompt()


    def reload_router(self) -> None:
        """Reload the router model and tools on the runtime"""
        import importlib
        import config
        importlib.reload()

        self.primary_model = config.ROUTER_PRIMARY_ROUTE
        self.router = Router(
            model_list=config.build_router_model_list(),
            fallbacks=config.ROUTER_FALLBACKS,
            set_verbose=False,
            num_retries=0,
        )


    def chat(self, user_input: str) -> None:
        """Send a user message and run the tool-calling loop.

        The response is streamed to the terminal. When the model requests
        tools, the calls are appended to the history together with their
        results and the model is asked again, up to
        config.MAX_TOOL_ITERATIONS rounds.

        Args:
            user_input: Raw text typed by the user.

        Returns:
            None
        """
        self.messages.append({"role": "user", "content": user_input})
        current_iteration = 0

        while current_iteration < config.MAX_TOOL_ITERATIONS:
            current_iteration += 1

            # Copy the history so the attached files can be injected into the
            # last user message without altering the stored conversation.
            messages_for_api = list(self.messages)

            files_context = self.context.get_combined_context() if hasattr(self, 'context') else ''

            if files_context and messages_for_api:
                for i in range(len(messages_for_api) - 1, -1, -1):
                    if messages_for_api[i].get('role') == 'user':
                        user_msg = messages_for_api[i].copy()
                        user_msg['content'] = f'{files_context}\n{user_msg["content"]}'
                        messages_for_api[i] = user_msg
                        break

            messages_for_api = prune_tool_message(
                messages=messages_for_api,
                keep_last_n=config.KEEP_RECENT_TOOL_OUTPUTS,
                preserve_chars=config.TOOL_STUBS
            )

            # The Router already knows the fallback chains; passing them again
            # here would duplicate the configuration.
            # print("\n--- ДИАГНОСТИКА СТРУКТУРЫ ДИАЛОГА ---")
            # for idx, m in enumerate(messages_for_api):
            #     role = m.get('role')
            #     has_tools = bool(m.get('tool_calls'))
            #     tool_id = m.get('tool_call_id')
            #     print(f"[{idx}] Role: {role} | has_tool_calls: {has_tools} | tool_call_id: {tool_id}")
            # print("------------------------------------\n")
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

            # Stream the answer, but only read fields that a chunk actually
            # carries: some providers send final chunks without choices.
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

                # The assistant turn must be stored before the tool results,
                # as required by the OpenAI-compatible message format.
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
                            raise ValueError("Tool arguments must be a JSON object")
                    except (json.JSONDecodeError, ValueError) as exc:
                        function_result = f"Invalid tool arguments: {exc}"
                    else:
                        print(
                            f"Calling function {function_name} "
                            f"with arguments {function_args}"
                        )

                        if function_name not in self.available_functions:
                            function_result = f"Error: function {function_name} not found"
                        else:
                            intercept_res = self.interceptor.intercept(
                                tool_name=function_name,
                                tool_args=function_args,
                                current_mode=self.mode,
                            )
                            if not intercept_res.allowed:
                                function_result = intercept_res.rejection_reason
                                print(f'\033[33m[BLOCKED]\033[0m {intercept_res.rejection_reason}')
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
                                        f"Error while executing {function_name}: {exc}"
                                    )

                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": str(function_result),
                        }
                    )

                # Ask the Router for the next model turn after the tool
                # results have been added to the history.
                continue

            self.messages.append(
                {"role": "assistant", "content": full_response}
            )
            return

        print(
            f"Tool iteration limit reached "
            f"({config.MAX_TOOL_ITERATIONS})."
        )

