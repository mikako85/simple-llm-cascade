"""Tests for the tool-iteration budget in ChatAgent.chat().

The tests replace the ``config`` module before ``agent`` is imported: the
real one reads ``~/.simple-llm-cascade/models.yaml`` at import time and would
start the interactive configuration wizard on a clean machine.
"""

import sys
import types

import pytest


# ---------------------------------------------------------------------------
# Fake streaming chunks, mirroring the shape returned by LiteLLM
# ---------------------------------------------------------------------------


class _FunctionDelta:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _ToolCallDelta:
    def __init__(self, index, call_id=None, name=None, arguments=None):
        self.index = index
        self.id = call_id
        self.function = _FunctionDelta(name, arguments)


class _Delta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, delta):
        self.delta = delta


class _Chunk:
    def __init__(self, delta):
        self.choices = [_Choice(delta)]


def final_answer(text: str = 'done') -> list:
    """Stream that returns plain text and no tool calls."""
    return [_Chunk(_Delta(content=text))]


def tool_round(*calls: tuple) -> list:
    """Stream requesting one or more tool calls within a single model round.

    Args:
        *calls: Tuples of (call_id, function_name, json_arguments).
    """
    chunks = []
    for index, (call_id, name, arguments) in enumerate(calls):
        chunks.append(
            _Chunk(_Delta(tool_calls=[_ToolCallDelta(index, call_id, name, arguments)]))
        )
    return chunks


class FakeRouter:
    """Router stand-in that replays scripted streams.

    Once the script is exhausted the last stream is repeated forever, which
    models a model that keeps calling tools and never answers.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        index = len(self.calls) - 1
        response = self._responses[index] if index < len(self._responses) else self._responses[-1]
        return iter(response)


class FakeContext:
    def get_combined_context(self) -> str:
        return ''


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_config(monkeypatch):
    """Install a stub ``config`` module and import ``agent`` against it."""
    module = types.ModuleType('config')
    module.MAX_TOOL_ITERATIONS = 3
    module.MAX_ITERATION_EXTENSIONS = 1
    module.KEEP_RECENT_TOOL_OUTPUTS = 20
    module.TOOL_STUBS = 1500
    module.TEMPERATURE = 0.7
    module.EXECUTION_MODE = 'yolo'
    module.ROUTER_PRIMARY_ROUTE = 'fake-route'

    monkeypatch.setitem(sys.modules, 'config', module)
    monkeypatch.delitem(sys.modules, 'agent', raising=False)
    return module


@pytest.fixture
def agent_module(fake_config):
    import agent as imported_agent

    return imported_agent


def bare_agent(agent_module):
    """ChatAgent instance without __init__: only the budget helpers are used."""
    return agent_module.ChatAgent.__new__(agent_module.ChatAgent)


def build_agent(agent_module, responses, mode=None, executed=None):
    """Create a ChatAgent instance without the real __init__ (no network)."""
    instance = agent_module.ChatAgent.__new__(agent_module.ChatAgent)
    instance.primary_model = 'fake-route'
    instance.mode = mode or agent_module.ExecutionMode.YOLO
    instance.messages = [{'role': 'system', 'content': 'system prompt'}]
    instance.router = FakeRouter(responses)
    instance.context = FakeContext()
    instance.interceptor = agent_module.ToolInterceptor(default_mode=instance.mode)

    log = executed if executed is not None else []

    def _record(name):
        def _run(**kwargs):
            log.append((name, kwargs))
            return f'{name}-result'

        return _run

    instance.available_functions = {
        'get_system_time': _record('get_system_time'),
        'list_directory': _record('list_directory'),
        'read_text_document': _record('read_text_document'),
    }
    instance.executed = log
    return instance


def assert_history_is_api_valid(messages):
    """Every tool result must answer a preceding tool_call, and no turn may end on a tool."""
    expected_ids: list[str] = []

    for message in messages:
        role = message.get('role')

        if role == 'assistant':
            assert not expected_ids, f'assistant answered before tool results: {expected_ids}'
            expected_ids = [call['id'] for call in (message.get('tool_calls') or [])]
        elif role == 'tool':
            assert message['tool_call_id'] in expected_ids, (
                f'tool result {message["tool_call_id"]} has no matching tool_calls'
            )
            expected_ids.remove(message['tool_call_id'])
        elif role == 'user':
            assert not expected_ids, f'user message while tool results were pending: {expected_ids}'

    assert messages[-1]['role'] != 'tool', 'history must not end on an unanswered tool result'


# ---------------------------------------------------------------------------
# Budget accounting
# ---------------------------------------------------------------------------


class TestIterationBudgetAccounting:
    def test_plain_answer_costs_one_round(self, agent_module, fake_config):
        chat_agent = build_agent(agent_module, [final_answer('hello')])

        chat_agent.chat('hi')

        assert len(chat_agent.router.calls) == 1
        assert chat_agent.messages[-1] == {'role': 'assistant', 'content': 'hello'}
        assert_history_is_api_valid(chat_agent.messages)

    def test_round_with_two_tools_costs_one_iteration(self, agent_module, fake_config):
        """A round is a model call, not a tool execution."""
        fake_config.MAX_TOOL_ITERATIONS = 2
        fake_config.MAX_ITERATION_EXTENSIONS = 0
        chat_agent = build_agent(
            agent_module,
            [
                tool_round(
                    ('call_1', 'get_system_time', '{}'),
                    ('call_2', 'list_directory', '{"path": "."}'),
                ),
                final_answer('both done'),
            ],
        )

        chat_agent.chat('do two things')

        assert len(chat_agent.router.calls) == 2
        assert [name for name, _ in chat_agent.executed] == ['get_system_time', 'list_directory']
        assert chat_agent.messages[-1]['content'] == 'both done'
        assert_history_is_api_valid(chat_agent.messages)

    def test_budget_is_reread_on_every_turn(self, agent_module, fake_config):
        """``/config`` reloads the config module, so limits must be re-read per turn."""
        fake_config.MAX_TOOL_ITERATIONS = 1
        fake_config.MAX_ITERATION_EXTENSIONS = 0
        chat_agent = build_agent(
            agent_module,
            [tool_round(('call_1', 'get_system_time', '{}'))],
        )

        chat_agent.chat('first turn')
        assert len(chat_agent.router.calls) == 1

        fake_config.MAX_TOOL_ITERATIONS = 3
        chat_agent.chat('second turn')
        assert len(chat_agent.router.calls) == 4


class TestBudgetExhaustion:
    def test_hard_stop_at_budget_when_extensions_disabled(self, agent_module, fake_config):
        fake_config.MAX_TOOL_ITERATIONS = 3
        fake_config.MAX_ITERATION_EXTENSIONS = 0
        chat_agent = build_agent(
            agent_module,
            [tool_round(('call_x', 'get_system_time', '{}'))],
        )

        chat_agent.chat('loop forever')

        assert len(chat_agent.router.calls) == 3
        assert len(chat_agent.executed) == 3

    def test_interruption_is_reported_not_silent(self, agent_module, fake_config, capsys):
        fake_config.MAX_TOOL_ITERATIONS = 2
        fake_config.MAX_ITERATION_EXTENSIONS = 0
        chat_agent = build_agent(
            agent_module,
            [tool_round(('call_x', 'get_system_time', '{}'))],
        )

        chat_agent.chat('loop forever')

        out = capsys.readouterr().out
        assert '[ITERATION LIMIT]' in out
        assert 'budget of 2 exhausted' in out

    def test_history_stays_valid_after_truncation(self, agent_module, fake_config):
        fake_config.MAX_TOOL_ITERATIONS = 2
        fake_config.MAX_ITERATION_EXTENSIONS = 0
        chat_agent = build_agent(
            agent_module,
            [tool_round(('call_x', 'get_system_time', '{}'))],
        )

        chat_agent.chat('loop forever')

        assert_history_is_api_valid(chat_agent.messages)
        assert chat_agent.messages[-1]['role'] == 'assistant'
        assert chat_agent.messages[-1]['content'].startswith('[cascade]')

        # The session must remain usable: the next turn is accepted by the fakes.
        chat_agent.router._responses = [final_answer('recovered')]
        chat_agent.chat('next question')
        assert chat_agent.messages[-1]['content'] == 'recovered'


class TestExtensionPolicy:
    def test_yolo_extends_silently_until_hard_cap(self, agent_module, fake_config, capsys):
        fake_config.MAX_TOOL_ITERATIONS = 2
        fake_config.MAX_ITERATION_EXTENSIONS = 2
        chat_agent = build_agent(
            agent_module,
            [tool_round(('call_x', 'get_system_time', '{}'))],
            mode=agent_module.ExecutionMode.YOLO,
        )

        chat_agent.chat('loop forever')

        # 2 rounds per budget, the initial budget plus 2 extensions.
        assert len(chat_agent.router.calls) == 2 * (1 + 2)
        assert len(chat_agent.executed) == 6
        assert '[YOLO]' in capsys.readouterr().out
        assert_history_is_api_valid(chat_agent.messages)

    def test_ask_mode_declined_extension_stops_turn(self, agent_module, fake_config, monkeypatch, capsys):
        fake_config.MAX_TOOL_ITERATIONS = 2
        fake_config.MAX_ITERATION_EXTENSIONS = 5
        prompts = []

        def decline(limit, total_rounds, extensions_left):
            prompts.append((limit, total_rounds, extensions_left))
            return False

        monkeypatch.setattr(agent_module.ChatAgent, 'ask_iteration_extension', staticmethod(decline))
        chat_agent = build_agent(
            agent_module,
            [tool_round(('call_x', 'get_system_time', '{}'))],
            mode=agent_module.ExecutionMode.ASK,
        )

        chat_agent.chat('loop forever')

        assert prompts == [(2, 2, 5)]
        assert len(chat_agent.router.calls) == 2
        out = capsys.readouterr().out
        assert 'Execution paused by user' in out
        assert_history_is_api_valid(chat_agent.messages)

    def test_ask_mode_accepted_extension_continues(self, agent_module, fake_config, monkeypatch):
        fake_config.MAX_TOOL_ITERATIONS = 2
        fake_config.MAX_ITERATION_EXTENSIONS = 1
        monkeypatch.setattr(
            agent_module.ChatAgent,
            'ask_iteration_extension',
            staticmethod(lambda **kwargs: True),
        )
        chat_agent = build_agent(
            agent_module,
            [tool_round(('call_x', 'get_system_time', '{}'))],
            mode=agent_module.ExecutionMode.ASK,
        )

        chat_agent.chat('loop forever')

        assert len(chat_agent.router.calls) == 4
        assert_history_is_api_valid(chat_agent.messages)

    def test_extension_helper_treats_eof_as_refusal(self, agent_module, monkeypatch):
        import prompt_toolkit

        def raise_eof(*args, **kwargs):
            raise EOFError

        monkeypatch.setattr(prompt_toolkit, 'prompt', raise_eof)
        assert agent_module.ChatAgent.ask_iteration_extension(5, 10, 2) is False


class TestBudgetConfiguration:
    def test_zero_budget_is_clamped_and_warns(self, agent_module, fake_config, capsys):
        fake_config.MAX_TOOL_ITERATIONS = 0

        assert bare_agent(agent_module).resolve_iteration_limits()[0] == 1
        assert 'would block every turn' in capsys.readouterr().err

    def test_zero_budget_does_not_swallow_the_turn(self, agent_module, fake_config):
        """A zero budget used to make chat() return without a single model call."""
        fake_config.MAX_TOOL_ITERATIONS = 0
        fake_config.MAX_ITERATION_EXTENSIONS = 0
        chat_agent = build_agent(agent_module, [final_answer('still answered')])

        chat_agent.chat('hello')

        assert len(chat_agent.router.calls) == 1
        assert chat_agent.messages[-1]['content'] == 'still answered'

    def test_invalid_budget_falls_back_to_default(self, agent_module, fake_config, capsys):
        fake_config.MAX_TOOL_ITERATIONS = 'not-a-number'
        fake_config.MAX_ITERATION_EXTENSIONS = 'nonsense'

        limit, extensions = bare_agent(agent_module).resolve_iteration_limits()

        assert limit == agent_module.ChatAgent.DEFAULT_MAX_ITERATIONS
        assert extensions == agent_module.ChatAgent.DEFAULT_MAX_EXTENSIONS
        assert 'Invalid max_tool_iterations' in capsys.readouterr().err

    def test_negative_extensions_are_ignored(self, agent_module, fake_config):
        fake_config.MAX_ITERATION_EXTENSIONS = -3

        assert bare_agent(agent_module).resolve_iteration_limits()[1] == 0
