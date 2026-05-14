from __future__ import annotations


def build_layer4(
    active_events: list[dict] | None = None,
    rules_appendix: str | None = None,
    foreshadowing_prompts: list[str] | None = None,
) -> dict | None:
    """
    Layer 4: Dynamic Events & Rules (on-demand injection).
    Only injects when there are active events, rules, or foreshadowing.

    Each event: {"name": str, "active_prompt": str | None, "rules_appendix": str | None}
    Returns None if nothing to inject (layer is skipped).
    """
    parts = []

    # Active event prompts
    if active_events:
        for ev in active_events:
            if ev.get("active_prompt"):
                parts.append(f"【当前事件：{ev['name']}】\n{ev['active_prompt']}")

    # Rule appendix (with strong LLM constraint)
    if rules_appendix:
        parts.append(rules_appendix)

    # Foreshadowing prompts (probabilistic injection)
    if foreshadowing_prompts:
        for fp in foreshadowing_prompts:
            parts.append(f"【流言/预兆】\n{fp}")

    if not parts:
        return None

    return {"role": "system", "content": "\n\n".join(parts)}
