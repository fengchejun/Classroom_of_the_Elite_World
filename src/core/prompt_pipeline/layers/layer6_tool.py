from __future__ import annotations


def build_layer6(tool_results: list[dict] | None = None) -> list[dict] | None:
    """
    Layer 6: Tool Feedback Injection (dynamic insertion).
    Inserts role: "tool" messages for LLM function calling results.

    Each result: {"tool_call_id": str, "name": str, "content": str}
    Returns list of tool messages or None.
    """
    if not tool_results:
        return None

    messages = []
    for tr in tool_results:
        messages.append({
            "role": "tool",
            "tool_call_id": tr.get("tool_call_id", "unknown"),
            "name": tr.get("name", "unknown"),
            "content": tr["content"],
        })
    return messages
