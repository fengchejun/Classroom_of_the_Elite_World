"""
4-Stage NPC Funnel Logic.

Replaces static NPC_SCHEDULES with dynamic NPC visibility:
  Stage 1: Lifecycle filter (availability)
  Stage 2: Zone dispatch (schedule_weights -> location)
  Stage 3: Spotlight selection (priority-based narrative focus)
  Stage 4: Hot context injection (dynamic brief_status replacement)
"""

from __future__ import annotations

import hashlib
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────────

UNAVAILABLE_TAGS = {"absent", "injured", "suspended", "expelled", "off_campus"}

CRITICAL_NPCS = {
    "堀北铃音", "龙园翔", "栉田桔梗", "轻井泽惠",
    "一之濑帆波", "坂柳有栖", "平田洋介",
}

# Map old location IDs (from characters.json) to new hierarchical IDs
_LOCATION_ALIASES: dict[str, str] = {
    "classroom_d": "classroom_1d",
    "classroom_1d": "classroom_1d",
    "cafeteria": "mall_cafeteria",
    "dormitory": "dorm_lobby",
    "school_field": "sports_field",
    "school_gymnasium": "gymnasium",
    "special_building": "special_building_1f",
    "hallway_1f": "hallway_1f",
    "library": "library",
    "rooftop": "rooftop",
}

# Default schedule weights per class, per time slot
DEFAULT_SCHEDULES: dict[str, dict[str, dict[str, float]]] = {
    "D": {
        "morning":  {"classroom_1d": 0.45, "hallway_2f": 0.2, "hallway_1f": 0.1,
                      "library": 0.1, "sports_field": 0.1, "rooftop": 0.05},
        "noon":     {"classroom_1d": 0.3, "mall_cafeteria": 0.35, "hallway_2f": 0.15,
                      "library": 0.1, "sports_field": 0.1},
        "dusk":     {"classroom_1d": 0.2, "sports_field": 0.25, "library": 0.2,
                      "hallway_1f": 0.15, "hallway_2f": 0.1, "mall_cafeteria": 0.1},
        "evening":  {"dorm_lobby": 0.15, "dorm_courtyard": 0.1, "mall_cafeteria": 0.2,
                      "library": 0.15, "sports_field": 0.15, "mall_entertainment": 0.1,
                      "mall_cafe": 0.1, "rooftop": 0.05},
        "late_night": {"dorm_lobby": 0.15, "dorm_male_floor": 0.1, "dorm_female_floor": 0.1,
                        "dorm_courtyard": 0.05},
    },
    "C": {
        "morning":  {"classroom_1c": 0.8, "hallway_3f": 0.2},
        "noon":     {"classroom_1c": 0.3, "mall_cafeteria": 0.3, "special_building_1f": 0.2, "hallway_3f": 0.2},
        "dusk":     {"special_building_1f": 0.4, "sports_field": 0.3, "classroom_1c": 0.3},
        "evening":  {"dorm_lobby": 0.15, "special_building_1f": 0.15, "mall_cafeteria": 0.2,
                      "sports_field": 0.15, "library": 0.1, "rooftop": 0.1,
                      "dorm_courtyard": 0.1, "mall_entertainment": 0.05},
        "late_night": {"dorm_lobby": 0.15, "dorm_male_floor": 0.1, "dorm_female_floor": 0.1,
                        "special_building_1f": 0.1},
    },
    "B": {
        "morning":  {"classroom_1b": 0.8, "hallway_2f": 0.2},
        "noon":     {"classroom_1b": 0.3, "mall_cafeteria": 0.4, "hallway_1f": 0.3},
        "dusk":     {"classroom_1b": 0.3, "mall_cafeteria": 0.2, "library": 0.3, "hallway_1f": 0.2},
        "evening":  {"dorm_lobby": 0.15, "mall_cafeteria": 0.2, "library": 0.2,
                      "sports_field": 0.15, "mall_entertainment": 0.1, "dorm_courtyard": 0.1,
                      "mall_cafe": 0.1},
        "late_night": {"dorm_lobby": 0.15, "dorm_male_floor": 0.1, "dorm_female_floor": 0.1,
                        "dorm_courtyard": 0.05},
    },
    "A": {
        "morning":  {"classroom_1a": 0.9, "hallway_2f": 0.1},
        "noon":     {"classroom_1a": 0.4, "mall_cafe": 0.3, "library": 0.3},
        "dusk":     {"classroom_1a": 0.3, "library": 0.5, "hallway_1f": 0.2},
        "evening":  {"dorm_lobby": 0.15, "library": 0.25, "mall_cafe": 0.2,
                      "mall_cafeteria": 0.15, "dorm_courtyard": 0.1, "mall_entertainment": 0.1,
                      "rooftop": 0.05},
        "late_night": {"dorm_lobby": 0.15, "dorm_male_floor": 0.1, "dorm_female_floor": 0.1,
                        "library": 0.1},
    },
}

FALLBACK_LOCATION = "classroom_1d"

# Trait-derived behavior hints
TRAIT_BEHAVIORS: dict[str, str] = {
    "孤高": "独自一人，与周围保持距离",
    "冷静": "神情平静，专注于自己的事",
    "社交达人": "正与周围的人谈笑风生",
    "观察者": "安静地观察着四周",
    "观察力强": "安静地观察着四周",
    "暴力": "散发着生人勿近的气场",
    "冲动": "显得坐立不安，随时可能爆发",
    "暴躁": "散发着生人勿近的气场",
    "文学少女": "沉浸在书本的世界里",
    "天才": "神情从容，似乎一切尽在掌握",
    "理性": "安静地思考着什么",
    "低调": "尽量不引人注目",
    "温柔": "微笑着关注着周围的一切",
    "开朗": "正活跃地与人交谈",
    "冷酷": "冷眼旁观着周围的一切",
    "善于伪装": "脸上挂着得体的微笑",
    "隐藏实力": "看起来平凡无奇",
}

TAG_BEHAVIORS: dict[str, str] = {
    "broke": "面露焦虑，频频查看手机余额",
    "injured": "动作小心，似乎身上有伤",
    "nervous": "神情紧张，时不时环顾四周",
    "calm": "神情平静，专注于自己的事",
    "excited": "显得很兴奋，活跃地与人交谈",
    "reading": "正在安静地读书",
    "studying": "正在认真学习",
    "chatting": "正与身边的人交谈",
    "sleeping": "趴在桌上睡觉",
    "training": "正在专注地训练",
    "wandering": "在附近徘徊",
}

RELATION_MAP: dict[str, str] = {
    "trust": "对你抱有信任",
    "hostile": "对你有明显的敌意",
    "subservient": "对你言听计从",
    "neutral": "与你的关系普通",
    "friend": "与你关系友好",
    "crush": "似乎对你有好感",
    "rival": "视你为竞争对手",
    "suspicious": "对你保持警惕",
}


# ── Helpers ─────────────────────────────────────────────────────────────────

def _deterministic_weighted_pick(weights: dict[str, float], seed_str: str) -> str:
    """Deterministic weighted random selection using hash seed."""
    locations = list(weights.keys())
    probs = list(weights.values())
    total = sum(probs)
    if total <= 0:
        return locations[0] if locations else FALLBACK_LOCATION
    probs = [p / total for p in probs]
    h = hashlib.md5(seed_str.encode()).digest()
    val = int.from_bytes(h[:4], "big") / 0xFFFFFFFF
    cumulative = 0.0
    for loc, p in zip(locations, probs):
        cumulative += p
        if val < cumulative:
            return loc
    return locations[-1]


def _translate_location_ids(weights: dict[str, float]) -> dict[str, float]:
    """Translate old location IDs in schedule_weights to new hierarchical IDs."""
    translated: dict[str, float] = {}
    for loc_id, prob in weights.items():
        new_id = _LOCATION_ALIASES.get(loc_id, loc_id)
        if new_id in translated:
            translated[new_id] += prob
        else:
            translated[new_id] = prob
    return translated


def _derive_behavior_from_status(status_tags: list[str], traits: list[str]) -> str:
    """Generate a dynamic behavior description from status tags and traits."""
    for tag in status_tags:
        if tag in TAG_BEHAVIORS:
            return TAG_BEHAVIORS[tag]
    for trait in traits:
        if trait in TRAIT_BEHAVIORS:
            return TRAIT_BEHAVIORS[trait]
    return "看起来和平常一样"


# ── Stage 1: Lifecycle Filter ──────────────────────────────────────────────

def filter_available_npcs(
    character_library: dict[str, Any],
    player_name: str,
    game_date: str = "2024-04-01",
) -> list[dict[str, Any]]:
    """Filter NPCs by lifecycle availability and enrollment year."""
    current_year = int(game_date[:4]) if game_date else 2024

    available: list[dict[str, Any]] = []
    for name, data in character_library.items():
        if name == player_name:
            continue
        status_tags = data.get("status_tags", [])
        if isinstance(status_tags, list):
            if any(tag in UNAVAILABLE_TAGS for tag in status_tags):
                continue

        # Enrollment year filter: only characters who have already enrolled
        enroll_year = data.get("enrollment_year", "2024")
        if enroll_year and enroll_year != "N/A":
            try:
                ey = int(str(enroll_year))
                if ey > current_year:
                    continue  # hasn't enrolled yet
            except (ValueError, TypeError):
                pass  # unparseable → allow (treat as N/A)

        available.append({
            "name": name,
            "role_id": data.get("role_id", ""),
            "class_name": data.get("class_name", ""),
            "enrollment_year": data.get("enrollment_year", "2024"),
            "traits": data.get("traits", []),
            "status_tags": status_tags if isinstance(status_tags, list) else [],
            "schedule_weights": data.get("schedule_weights"),
            "dorm_room_id": data.get("dorm_room_id", ""),
            "relations": data.get("relations", []),
            "secrets": data.get("secrets", []),
            "public_info": data.get("public_info", []),
            "private_points": data.get("private_points", 0),
            "spending_habit": data.get("spending_habit", "normal"),
        })
    return available


# ── Stage 2: Zone Dispatch ─────────────────────────────────────────────────

def dispatch_to_locations(
    available_npcs: list[dict[str, Any]],
    game_date: str,
    time_slot: str,
    ai_managed_npcs: dict[str, str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Assign each available NPC to a location based on schedule_weights.

    If ai_managed_npcs is provided, NPCs listed in it are placed at the AI-assigned
    location instead of using schedule_weights. This enables the Variable AI to
    overwrite NPC positions for hot zone characters.
    """
    location_map: dict[str, list[dict[str, Any]]] = {}

    for npc in available_npcs:
        # If AI has explicitly placed this NPC, use that location
        if ai_managed_npcs and npc["name"] in ai_managed_npcs:
            forced_loc = ai_managed_npcs[npc["name"]]
            if forced_loc:
                location_map.setdefault(forced_loc, []).append(npc)
                continue

        weights = npc.get("schedule_weights")
        slot_weights: dict[str, float] = {}

        if weights and isinstance(weights, dict):
            raw = weights.get(time_slot, {})
            if raw:
                slot_weights = _translate_location_ids(raw)

        if not slot_weights:
            class_name = npc.get("class_name", "D")
            class_defaults = DEFAULT_SCHEDULES.get(class_name, DEFAULT_SCHEDULES["D"])
            slot_weights = class_defaults.get(time_slot, {FALLBACK_LOCATION: 1.0})

        # Inject dorm room weight: in evening/late_night, NPCs with a dorm room
        # strongly prefer their own room over the lobby, eliminating lobby crowding.
        dorm_room = npc.get("dorm_room_id", "")
        if dorm_room and time_slot in ("evening", "late_night"):
            adjusted: dict[str, float] = {}
            for loc, w in slot_weights.items():
                if loc == "dorm_lobby":
                    adjusted[loc] = w * 0.15  # drastically reduce lobby presence
                else:
                    adjusted[loc] = w
            adjusted[dorm_room] = adjusted.get(dorm_room, 0.0) + 0.7
            slot_weights = adjusted

        seed = f"{game_date}|{time_slot}|{npc['name']}"
        location = _deterministic_weighted_pick(slot_weights, seed)

        location_map.setdefault(location, []).append(npc)

    return location_map


# ── Stage 3: Spotlight Selection ───────────────────────────────────────────

def select_spotlight(
    npc_location_map: dict[str, list[dict[str, Any]]],
    player_location_id: str,
    player_name: str,
    character_library: dict[str, Any],
    max_spotlight: int = 4,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select which NPCs at the player's location get narrative spotlight."""
    npcs_here = npc_location_map.get(player_location_id, [])
    if not npcs_here:
        return [], []

    player_data = character_library.get(player_name, {})
    player_role_id = player_data.get("role_id", "")

    scored: list[dict[str, Any]] = []
    for npc in npcs_here:
        priority: float = 0.0
        is_critical = False

        if npc["name"] in CRITICAL_NPCS:
            is_critical = True
            priority += 100

        relations = npc.get("relations", [])
        if isinstance(relations, list):
            for r in relations:
                if r.get("to") == player_name:
                    priority += 50
                    break

        secrets = npc.get("secrets", [])
        if isinstance(secrets, list):
            for s in secrets:
                known_by = s.get("known_by", [])
                if isinstance(known_by, list):
                    if player_name in known_by or player_role_id in known_by:
                        priority += 30
                        break

        h = hashlib.md5(f"{npc['name']}_spotlight".encode()).digest()
        noise = int.from_bytes(h[:2], "big") / 0xFFFF
        priority += noise * 10

        scored.append({**npc, "priority": priority, "is_critical": is_critical})

    scored.sort(key=lambda x: x["priority"], reverse=True)

    spotlight = scored[:max_spotlight]
    background = scored[max_spotlight:]

    return spotlight, background


# ── Stage 4: Hot Context Injection ─────────────────────────────────────────

def _build_single_context(
    npc: dict[str, Any],
    character_library: dict[str, Any],
    player_name: str,
    is_spotlight: bool,
) -> str:
    """Build a single NPC's one-line context string."""
    name = npc["name"]
    class_name = npc.get("class_name", "?")
    traits = npc.get("traits", [])
    trait_str = "·".join(traits[:2]) if traits else ""

    marker = "★" if is_spotlight else "·"

    parts = [f"{name}[{class_name}班"]
    if trait_str:
        parts.append(f"·{trait_str}")
    parts.append("]")
    identity = "".join(parts)

    details: list[str] = []

    relations = npc.get("relations", [])
    if isinstance(relations, list):
        for r in relations:
            if r.get("to") == player_name:
                rel_type = r.get("type", "")
                rel_text = RELATION_MAP.get(rel_type, f"与你的关系：{rel_type}")
                details.append(rel_text)
                break

    public_info = npc.get("public_info", [])
    if isinstance(public_info, list) and public_info:
        first = public_info[0]
        if isinstance(first, dict):
            snippet = first.get("content", "")
            if len(snippet) > 40:
                snippet = snippet[:37] + "..."
            details.append(snippet)

    status_tags = npc.get("status_tags", [])
    behavior = _derive_behavior_from_status(
        status_tags if isinstance(status_tags, list) else [],
        traits,
    )
    if behavior:
        details.append(behavior)

    detail_str = "。" if not details else ""
    if details:
        detail_str = "：" + "；".join(details[:2])

    return f"{marker} {identity}{detail_str}"


def build_context(
    spotlight_npcs: list[dict[str, Any]],
    background_npcs: list[dict[str, Any]],
    character_library: dict[str, Any],
    player_name: str,
    max_background: int = 6,
) -> tuple[str, str]:
    """Build spotlight and background context text blocks."""
    spotlight_lines = [
        _build_single_context(n, character_library, player_name, True)
        for n in spotlight_npcs
    ]
    # Limit background NPCs to avoid overwhelming the LLM
    bg_to_show = background_npcs[:max_background]
    background_lines = [
        _build_single_context(n, character_library, player_name, False)
        for n in bg_to_show
    ]
    if len(background_npcs) > max_background:
        background_lines.append(f"· ...以及其他{len(background_npcs) - max_background}名同学在附近")

    spotlight_text = (
        "【核心在场角色】\n" + "\n".join(spotlight_lines)
        if spotlight_lines else ""
    )
    background_text = (
        "【其他在场角色】\n" + "\n".join(background_lines)
        if background_lines else ""
    )

    return spotlight_text, background_text


# ── Orchestrator ───────────────────────────────────────────────────────────

def run_npc_funnel(
    character_library: dict[str, Any],
    player_name: str,
    player_location_id: str,
    game_date: str,
    time_slot: str,
    max_spotlight: int = 4,
    ai_managed_npcs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run the complete 4-stage NPC funnel.

    If ai_managed_npcs is provided, NPCs with AI-assigned locations are placed
    at those positions instead of using schedule_weights (hot zone override).

    Returns:
        dict with:
          spotlight_npcs   - NPCs with narrative focus (with priority, is_critical)
          background_npcs  - NPCs present but in background
          spotlight_text   - LLM-ready spotlight context
          background_text  - LLM-ready background context
          all_at_location  - list of all NPC names at player location
    """
    available = filter_available_npcs(character_library, player_name, game_date)

    location_map = dispatch_to_locations(available, game_date, time_slot, ai_managed_npcs)

    spotlight, background = select_spotlight(
        location_map, player_location_id, player_name,
        character_library, max_spotlight,
    )

    spotlight_text, background_text = build_context(
        spotlight, background, character_library, player_name,
    )

    all_here = location_map.get(player_location_id, [])

    return {
        "spotlight_npcs": spotlight,
        "background_npcs": background,
        "spotlight_text": spotlight_text,
        "background_text": background_text,
        "all_at_location": [n["name"] for n in all_here],
        "_location_map": {lid: [n["name"] for n in npcs] for lid, npcs in location_map.items()},
    }
