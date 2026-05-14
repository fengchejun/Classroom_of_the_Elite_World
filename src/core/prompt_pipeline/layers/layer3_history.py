from __future__ import annotations


def build_layer3(
    recent_dialogues: list[dict],
    story_summaries: list[str],
) -> dict:
    """
    Layer 3: Historical dialogue review.
    Injects the last N dialogues and all previously generated story summaries.
    Each dialogue: {"user": str, "llm": str}
    """
    parts = []

    if story_summaries:
        parts.append("【已发生的剧情总结】")
        for i, summary in enumerate(story_summaries, 1):
            parts.append(f"{i}. {summary}")

    if recent_dialogues:
        parts.append("\n【最近对话记录】")
        for i, d in enumerate(recent_dialogues, 1):
            parts.append(f"--- 第{i}轮 ---")
            parts.append(f"玩家: {d['user']}")
            # Truncate LLM response to avoid context overload
            llm_text = d['llm']
            if len(llm_text) > 300:
                llm_text = llm_text[:300] + "..."
            parts.append(f"叙述: {llm_text}")

    content = "\n".join(parts) if parts else "【无历史记录】"
    return {"role": "user", "content": content}
