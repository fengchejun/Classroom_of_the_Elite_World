from __future__ import annotations


def build_layer5(
    game_date: str,
    time_slot: str,
    spotlight_npcs: list[dict],
    player_stats: dict | None = None,
) -> dict:
    """
    Layer 5: Real-time State (Hot Context).
    Injects current time and spotlight NPC brief status.

    spotlight_npcs: [{"name": str, "brief_status": str, "is_critical": bool}, ...]
    """
    time_display = {
        "morning": "上午",
        "noon": "中午",
        "dusk": "傍晚",
        "evening": "晚上",
        "late_night": "深夜",
    }
    time_str = f"{game_date} {time_display.get(time_slot, time_slot)}"

    parts = [f"【当前时间】{time_str}"]

    if player_stats:
        parts.append(f"【个人状态】班级点数: {player_stats.get('class_points', 0)} | 私人点数: {player_stats.get('private_points', 0)}")

    if spotlight_npcs:
        parts.append("【在场角色】")
        for npc in spotlight_npcs:
            marker = "★" if npc.get("is_critical") else "·"
            parts.append(f"{marker} {npc['name']}：{npc['brief_status']}")
    else:
        parts.append("【在场角色】周围没有其他人。")

    return {"role": "system", "content": "\n".join(parts)}
