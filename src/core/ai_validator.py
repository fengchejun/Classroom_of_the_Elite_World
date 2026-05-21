"""
AI Output Validator.

Validates every AI-generated response before it reaches the game state:
  - Tool call arguments (before execution)
  - JSON structure and field types (after parsing)
  - state_changes correctness (location existence, reachability, time/date format)
  - choices structure

On failure: returns specific error messages that are fed back to the LLM for retry.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.core.time_engine.clock import TIME_SLOTS

# ── Tool argument schemas (subset of TOOL_DEFINITIONS for validation) ──────

TOOL_ARG_SCHEMAS: dict[str, dict] = {
    "get_character_info": {
        "required": ["char_name"],
        "types": {"char_name": str},
    },
    "query_location_info": {
        "required": ["location_id"],
        "types": {"location_id": str},
    },
    "check_exam_rules": {
        "required": ["keyword"],
        "types": {"keyword": str},
    },
    "get_exam_rules": {
        "required": ["keyword"],
        "types": {"keyword": str},
    },
    "get_upcoming_events": {
        "required": [],
        "types": {"count": int, "game_date": str},
    },
    "get_worldview_info": {
        "required": [],
        "types": {},
    },
    "transfer_points": {
        "required": ["target_char", "amount", "reason"],
        "types": {"target_char": str, "amount": (int, float), "reason": str},
    },
    "update_character_data": {
        "required": ["char_name", "data"],
        "types": {"char_name": str, "data": dict},
    },
}

VALID_TOOL_NAMES = set(TOOL_ARG_SCHEMAS.keys())


# ── Tool Call Validation ──────────────────────────────────────────────────

def validate_tool_call(tool_name: str, arguments: dict) -> tuple[bool, str]:
    """Validate a tool call before execution.

    Returns (valid, error_message).
    """
    # Check 1: function exists
    if tool_name not in VALID_TOOL_NAMES:
        return False, f"未知的工具名称: '{tool_name}'，可用工具: {sorted(VALID_TOOL_NAMES)}"

    schema = TOOL_ARG_SCHEMAS[tool_name]
    required = schema.get("required", [])
    types = schema.get("types", {})

    # Check 2: required arguments present
    for arg_name in required:
        if arg_name not in arguments:
            return False, f"工具 '{tool_name}' 缺少必需参数: '{arg_name}'"

    # Check 3: argument types
    for arg_name, arg_value in arguments.items():
        if arg_name in types:
            expected = types[arg_name]
            if not isinstance(arg_value, expected):
                type_name = expected.__name__ if isinstance(expected, type) else " | ".join(t.__name__ for t in expected)
                actual_name = type(arg_value).__name__
                return False, f"工具 '{tool_name}' 的参数 '{arg_name}' 类型错误：期望 {type_name}，收到 {actual_name} (值: {repr(arg_value)})"

    # Check 4: string args non-empty
    for arg_name in required:
        if arg_name in arguments and types.get(arg_name) == str:
            if not isinstance(arguments[arg_name], str) or not arguments[arg_name].strip():
                return False, f"工具 '{tool_name}' 的参数 '{arg_name}' 不能为空字符串"

    # Check 5: amount must be non-zero for transfer_points
    if tool_name == "transfer_points":
        amount = arguments.get("amount")
        if amount is not None:
            if isinstance(amount, (int, float)):
                if amount == 0:
                    return False, f"transfer_points 的 amount 不能为0"
            else:
                return False, f"transfer_points 的 amount 必须为数字，收到: {repr(amount)}"

    # Check 6: data must be non-empty dict for update_character_data
    if tool_name == "update_character_data":
        data = arguments.get("data")
        if not isinstance(data, dict) or not data:
            return False, f"update_character_data 的 data 必须是非空的JSON对象"

    return True, ""


# ── Response Validation ───────────────────────────────────────────────────

def validate_llm_response(
    parsed: dict,
    current_location_id: str = "",
    locations: dict | None = None,
    check_reachability: bool = True,
) -> tuple[bool, str]:
    """Validate the final parsed LLM response.

    Args:
        parsed: Dict from _parse_llm_content()
        current_location_id: Player's current location ID
        locations: LOCATIONS dict for validating location existence and reachability
        check_reachability: Whether to enforce connected_to reachability

    Returns (valid, error_message).
    """
    if locations is None:
        locations = {}

    errors: list[str] = []

    # -- Top-level structure --
    if not isinstance(parsed, dict):
        return False, "AI回复不是有效的JSON对象"

    if not parsed.get("narrative") or not isinstance(parsed.get("narrative"), str):
        errors.append("缺少 narrative 字段或 narrative 为空")
    elif len(parsed["narrative"].strip()) < 10:
        errors.append("narrative 内容过短，至少需要10个字符")

    # -- Choices validation --
    choices = parsed.get("choices", [])
    if choices is not None:
        if not isinstance(choices, list):
            errors.append(f"choices 必须是数组，收到: {type(choices).__name__}")
        else:
            for i, choice in enumerate(choices):
                if not isinstance(choice, dict):
                    errors.append(f"choices[{i}] 必须是对象，收到: {type(choice).__name__}")
                    continue
                if "id" not in choice:
                    errors.append(f"choices[{i}] 缺少 'id' 字段")
                elif not isinstance(choice["id"], str):
                    errors.append(f"choices[{i}].id 必须是字符串")
                if "text" not in choice:
                    errors.append(f"choices[{i}] 缺少 'text' 字段")
                elif not choice["text"] or not isinstance(choice["text"], str):
                    errors.append(f"choices[{i}].text 不能为空")

    # -- state_changes validation --
    state_changes = parsed.get("state_changes", {})
    if state_changes and isinstance(state_changes, dict):
        errors.extend(_validate_state_changes(state_changes, current_location_id, locations, check_reachability))
    elif state_changes is not None and not isinstance(state_changes, dict):
        errors.append(f"state_changes 必须是对象，收到: {type(state_changes).__name__}")

    if errors:
        return False, "\n".join(f"• {e}" for e in errors)
    return True, ""


def _validate_state_changes(
    changes: dict,
    current_location_id: str,
    locations: dict,
    check_reachability: bool,
) -> list[str]:
    """Validate state_changes fields. Returns list of error strings."""
    errors: list[str] = []

    new_location_id = changes.get("new_location_id")
    if new_location_id:
        if not isinstance(new_location_id, str):
            errors.append(f"new_location_id 必须是字符串，收到: {type(new_location_id).__name__}")
        elif locations and new_location_id not in locations:
            errors.append(
                f"new_location_id '{new_location_id}' 不存在于地点列表中"
            )
        elif locations and current_location_id and check_reachability:
            # Skip reachability if sleep_to_morning (always moves to dorm)
            if not changes.get("sleep_to_morning"):
                current_loc = locations.get(current_location_id, {})
                connected = current_loc.get("connected_to", [])
                if new_location_id not in connected and new_location_id != current_location_id:
                    connected_names = [
                        f"{cid}({locations.get(cid, {}).get('name', cid)})"
                        for cid in connected
                    ]
                    errors.append(
                        f"new_location_id '{new_location_id}' 无法从当前位置 '{current_location_id}' 直接到达。"
                        f"可到达的地点: {', '.join(connected_names) if connected_names else '无'}"
                    )

    new_time_slot = changes.get("new_time_slot")
    if new_time_slot:
        if not isinstance(new_time_slot, str):
            errors.append(f"new_time_slot 必须是字符串")
        elif new_time_slot not in TIME_SLOTS:
            errors.append(
                f"new_time_slot '{new_time_slot}' 无效，可选值: {', '.join(TIME_SLOTS)}"
            )

    new_game_date = changes.get("new_game_date")
    if new_game_date:
        if not isinstance(new_game_date, str):
            errors.append(f"new_game_date 必须是字符串")
        elif len(new_game_date) != 10:
            errors.append(f"new_game_date '{new_game_date}' 格式错误，应为 YYYY-MM-DD")
        else:
            try:
                datetime.strptime(new_game_date, "%Y-%m-%d")
            except ValueError:
                errors.append(f"new_game_date '{new_game_date}' 不是有效的日期，格式应为 YYYY-MM-DD")

    advance_slots = changes.get("advance_slots")
    if advance_slots is not None:
        if not isinstance(advance_slots, (int, float)):
            errors.append(f"advance_slots 必须为数字，收到: {type(advance_slots).__name__}")
        elif advance_slots <= 0 or advance_slots > 4:
            errors.append(f"advance_slots 必须在1-4之间，收到: {advance_slots}")

    sleep_to_morning = changes.get("sleep_to_morning")
    if sleep_to_morning is not None and not isinstance(sleep_to_morning, bool):
        errors.append(f"sleep_to_morning 必须为布尔值，收到: {type(sleep_to_morning).__name__}")

    return errors


# ── Error Prompt Builder ──────────────────────────────────────────────────

def build_validation_error_prompt(errors: list[str]) -> str:
    """Build a prompt telling the LLM what it did wrong, for retry."""
    numbered = "\n".join(f"{i+1}. {e}" for i, e in enumerate(errors))
    return f"""你的上一次回复存在以下问题：

{numbered}

请修正这些问题并重新生成你的回复。确保：
- JSON格式正确，包含 narrative、choices、state_changes 三个字段
- 所有地点ID必须在可用地点列表中，且从当前地点可直接到达（通过 connected_to 连接）
- 时间段必须是 morning/noon/dusk/evening/late_night 之一
- 日期格式必须是 YYYY-MM-DD（如 2024-04-01）
- choices 中每一项必须有 id 和 text 字段"""
