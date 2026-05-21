from __future__ import annotations

import json

import httpx

from src.config.settings import settings
from src.core.variable_agent.prompt import VARIABLE_AGENT_SYSTEM_PROMPT
from src.utils.logger import get_logger

logger = get_logger(__name__)


def build_hot_zone_npc_context(
    hot_zone_npcs: list[dict],
    player_name: str,
) -> str:
    """Build a compact profile block for hot zone NPCs to send to the Variable Agent."""
    if not hot_zone_npcs:
        return ""

    lines = ["【热区NPC列表 - 请为每个NPC主动推断当前行为】"]
    for npc in hot_zone_npcs:
        name = npc.get("name", "")
        class_name = npc.get("class_name", "?")
        traits = npc.get("traits", [])
        trait_str = "、".join(traits[:3]) if traits else "无"
        status_tags = npc.get("status_tags", [])
        status_str = "、".join(status_tags) if status_tags else "正常"
        current_loc = npc.get("current_location_id", "未知")
        dorm_room = npc.get("dorm_room_id", "")

        parts = [
            f"\n- {name}[{class_name}班] | 性格：{trait_str} | 状态：{status_str} | 当前位置：{current_loc}"
        ]
        if dorm_room:
            parts.append(f" | 宿舍房间：{dorm_room}")

        # Relations with player
        relations = npc.get("relations", [])
        if isinstance(relations, list):
            for r in relations:
                if r.get("to") == player_name:
                    rel_type = r.get("type", "neutral")
                    rel_map = {"trust": "信任", "hostile": "敌对", "subservient": "从属", "neutral": "中立"}
                    parts.append(f" | 对玩家：{rel_map.get(rel_type, rel_type)}")
                    break

        # Secrets known about player
        secrets = npc.get("secrets", [])
        if isinstance(secrets, list):
            for s in secrets:
                known_by = s.get("known_by", [])
                if isinstance(known_by, list) and player_name in known_by:
                    snippet = s.get("content", "")[:30]
                    parts.append(f" | 知道玩家的秘密：{snippet}...")
                    break

        lines.append("".join(parts))

    return "\n".join(lines)


async def extract_variable_changes(
    narrative: str,
    current_state: dict,
    character_names: list[str] | None = None,
    secret_info_ids: dict[str, list[dict]] | None = None,
    hot_zone_npcs: list[dict] | None = None,
) -> dict:
    """
    Call the Variable Agent LLM to extract state changes from narrative text.
    Uses a small, focused LLM call with low temperature for consistent extraction.
    """
    if not narrative or not narrative.strip():
        return _empty_changes()

    # Build context for Variable Agent
    char_name_hint = ""
    if character_names:
        char_name_hint = f"\n已知角色列表：{', '.join(character_names)}"

    # Build available secrets hint for accurate secret_info_id matching
    secrets_hint = ""
    if secret_info_ids:
        secrets_lines = []
        for owner_name, secrets_list in secret_info_ids.items():
            for s in secrets_list:
                secrets_lines.append(
                    f"    {s['info_id']}（{owner_name}的秘密）: {s['content'][:80]}"
                )
        if secrets_lines:
            secrets_hint = "\n已知秘密ID（检测秘密传播时请精确使用这些info_id）：\n" + "\n".join(secrets_lines)

    # Build hot zone NPC context
    hot_zone_hint = ""
    if hot_zone_npcs:
        hot_zone_hint = "\n\n" + build_hot_zone_npc_context(
            hot_zone_npcs,
            current_state.get("player_name", ""),
        )

    user_message = f"""【当前游戏状态】
日期：{current_state.get('game_date', '')}
时间：{current_state.get('time_slot', '')}
位置：{current_state.get('location_id', '')}
玩家：{current_state.get('player_name', '')}{char_name_hint}{secrets_hint}{hot_zone_hint}

【叙事文本】
{narrative}

请从上述叙事文本中提取所有变量变化。"""

    messages = [
        {"role": "system", "content": VARIABLE_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "messages": messages,
                    "max_tokens": 1536,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Variable Agent API call failed: {e}")
        return _empty_changes()

    # Parse JSON response
    try:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(l for l in lines if not l.startswith("```"))
        result = json.loads(cleaned)
        # Ensure all expected keys exist
        defaults = _empty_changes()
        for key in defaults:
            if key not in result:
                result[key] = defaults[key]
        logger.debug(f"Variable Agent extracted changes: {json.dumps(result, ensure_ascii=False)}")
        return result
    except json.JSONDecodeError:
        logger.warning(f"Variable Agent returned invalid JSON: {content[:200]}")
        return _empty_changes()


def _empty_changes() -> dict:
    return {
        "new_time_slot": None,
        "new_game_date": None,
        "new_location_id": None,
        "sleep_to_morning": False,
        "private_points_delta": 0,
        "class_points_delta": 0,
        "npc_point_changes": [],
        "relation_changes": [],
        "npc_status_changes": [],
        "npc_location_changes": [],
        "new_events": [],
        "secret_knowledge_changes": [],
        "hot_npc_behaviors": [],
    }
