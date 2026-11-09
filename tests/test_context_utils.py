import pytest
from context_utils import prune_tool_message


class TestSmartContextPruning:
    """Testing smart, adaptive context trimming for tools"""
    def test_no_pruning_when_under_max_total_chars(self):
        """If the total volume of the context is <= 120,000 characters, the messages are not truncated at all."""
        messages = [
            {'role': 'user', 'content': 'Analyze the codebase'}
        ]

        file_content = "def test_func():\n    return 'valid python code'\n" * 50  # ~2.2 KB
        for i in range(25):
            messages.append({
                'role': 'assistant',
                'content': None,
                'tool_calls': [{'id': f'call_{i}'}]
            })
            messages.append({
                'role': 'tool',
                'tool_call_id': f'call_{i}',
                'content': file_content
            })

        result = prune_tool_message(messages, keep_last_n=20, max_total_chars=120000)

        for msg in result:
            if msg.get('role') == 'tool':
                assert '[Output truncated]' not in msg['content']
                assert msg['content'] == file_content


    def test_pruning_triggers_when_budget_exceeded(self):
        """When the 120 KB limit is exceeded, older messages (> 20) are carefully compressed."""
        messages = [
            {'role': 'user', 'content': 'Heavy processing task'}
        ]

        large_content = 'LOG_LINE ' + ('x' * 100) + '\n'
        large_content = large_content * 90

        for i in range(25):
            messages.append({
                'role': 'assistant',
                'content': None,
                'tool_calls': [{'id': f'call_{i}'}]
            })
            messages.append({
                'role': 'tool',
                'tool_call_id': f'call_{i}',
                'content': large_content
            })

        result = prune_tool_message(messages,
                                    keep_last_n=20,
                                    preserve_chars=1500,
                                    max_total_chars=120000)

        tool_messages = [m for m in result if m.get('role') == 'tool']
        assert len(tool_messages) == 25

        for recent_tool in tool_messages[5:]:
            assert '[Output truncated]' not in recent_tool['content']
            assert len(recent_tool['content']) == len(large_content)

        for older_tool in tool_messages[:5]:
            assert '[Output truncated to save context]' in older_tool['content']
            assert len(older_tool['content']) < 1700
            assert older_tool['tool_call_id'].startswith('call_')


    def test_non_tool_messages_never_pruned(self):
        """Messages from the user and the assistant must never be modified."""
        user_text = 'Important Instructions: ' + ('A' * 150_000)
        messages = [
            {'role': 'user', 'content': user_text},
            {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'small content'},
        ]

        result = prune_tool_message(messages, max_total_chars=120_000)
        assert result[0]['content'] == user_text
        

    def test_immutability_of_input_list(self):
        """The original list of messages must not be mutated in place."""
        original_content = 'X' * 150000
        messages = [
            {'role': 'tool', 'tool_call_id': 'call_1', 'content': original_content},
        ]

        result = prune_tool_message(messages, keep_last_n=0, max_total_chars=100)

        assert '[Output truncated to save context]' in result[0]['content']
        assert messages[0]['content'] == original_content