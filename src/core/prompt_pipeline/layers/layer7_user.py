from __future__ import annotations


def build_layer7(user_input: str, choice_id: str | None = None) -> dict:
    """
    Layer 7: Player input.
    The actual text the player typed, or a UI option callback.
    """
    return {"role": "user", "content": user_input}
