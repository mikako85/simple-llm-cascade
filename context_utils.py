"""Utilities for managing and optimizing model_context"""

from typing import Any


def prune_tool_message(
    messages: list[dict[str, Any]],
    keep_last_n: int = 20,
    preserve_chars: int = 1500,
    max_total_chars: int = 120000,
) -> list[dict[str, Any]]:
    """Prune older tool execution outputs to prevent context overflow

    Iterates throught the message history in reverse order. The most recent
    'keep_last_n' tool messages are preserved intact. Any tool messages
    prior to that have their `content` truncated to a preview stub.

    The original `nessages` list and unmodified message dicts are not mutated.
    All required fields like `tool_call_id` remain intact to maintain API validity.

    Args:
        messages (list[dict[str, Any]]): Full conversation history.
        keep_last_n (int, optional): Number of most recent tool responses to keep in full.
        preserve_chars (int, optional): Number of leading characters from the original output
            to keep as a preview

    Returns:
        A new list of messages with older tool outputs safely truncated
    """

    if keep_last_n < 0:
        keep_last_n = 0

    total_chars = sum(len(str(m.get('content', ) or '')) for m in messages)

    if total_chars <= max_total_chars:
        return messages

    tool_count = 0
    optimized_reversed = []

    for msg in reversed(messages):
        if msg.get('role') == 'tool':
            tool_count += 1
            if tool_count > keep_last_n:
                raw_content = msg.get('content', '')

                stub_marker = (
                    '\n... [Output truncated to save context]'
                    'Tool execution was succesful and analyzed in prior turns'
                )

                min_threshold_to_prune = preserve_chars + len(stub_marker)
                if len(raw_content) > min_threshold_to_prune:
                    preview = raw_content[:preserve_chars].rstrip()
                    pruned_content = f'{preview}{stub_marker}'

                    pruned_msg = dict(msg)
                    pruned_msg['content'] = pruned_content
                    optimized_reversed.append(pruned_msg)
                    continue

        optimized_reversed.append(msg)
    optimized_reversed.reverse()
    return optimized_reversed
