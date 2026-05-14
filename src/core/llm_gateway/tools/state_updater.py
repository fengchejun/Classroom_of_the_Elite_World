from __future__ import annotations

import json

from src.core.llm_gateway.tool_registry import ToolDefinition

# Handler will be set at runtime after session/character managers are created
_state_updater_handler = None


def get_state_updater_definition() -> ToolDefinition:
    return ToolDefinition(
        name="update_player_state",
        description="更新玩家的位置或时间。当玩家表达移动或等待意图时调用此工具。例如'我去天台'、'我睡了一觉'、'我等了一会儿'等。",
        parameters={
            "new_location": {
                "type": "string",
                "description": "目标地点ID。如果玩家只是等待而没有移动，留空。",
            },
            "time_advance_slots": {
                "type": "integer",
                "description": "要推进的时间段数（morning->noon->dusk->evening->late_night->morning）。默认0表示不推进。",
            },
        },
        handler=None,
    )


async def handle_update_player_state(
    session_id: str,
    new_location: str | None = None,
    time_advance_slots: int = 0,
    **kwargs,
) -> str:
    """
    Handler implementation. Updates player location and/or advances time.
    Returns the new state and any triggered events as JSON.
    """
    # This is a placeholder - the actual implementation is wired up
    # at runtime to access the game service and database session.
    result = {
        "status": "ok",
        "new_location": new_location,
        "time_advanced_slots": time_advance_slots,
    }
    return json.dumps(result, ensure_ascii=False)
