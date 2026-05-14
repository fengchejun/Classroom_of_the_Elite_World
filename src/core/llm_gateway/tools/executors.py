from __future__ import annotations

import json

from src.core.llm_gateway.tool_registry import ToolDefinition
from src.utils.logger import get_logger

logger = get_logger(__name__)


def transfer_points_definition() -> ToolDefinition:
    return ToolDefinition(
        name="transfer_points",
        description="在玩家与NPC达成交易、赠送或赌约结算时执行私人点数的转移。正数表示玩家付出点数，负数表示玩家收到点数。",
        parameters={
            "target_char": {
                "type": "string",
                "description": "目标角色的名字或role_id",
            },
            "amount": {
                "type": "integer",
                "description": "转移的点数金额。正数=玩家付出，负数=玩家收入。",
            },
        },
        handler=None,
    )


def reveal_secret_definition() -> ToolDefinition:
    return ToolDefinition(
        name="reveal_secret",
        description="当剧情中玩家角色正式得知某个秘密时，解锁该秘密。例如从NPC口中得知、亲眼目睹、找到证据等。",
        parameters={
            "secret_id": {
                "type": "string",
                "description": "秘密的info_id",
            },
            "known_by": {
                "type": "array",
                "items": {"type": "string"},
                "description": "新增知晓此秘密的角色role_id列表。至少包含'player'如果玩家知道了的话。",
            },
        },
        handler=None,
    )


def update_relation_definition() -> ToolDefinition:
    return ToolDefinition(
        name="update_relation",
        description="当角色之间的关系发生显著变化时调用。例如结盟、决裂、某人开始畏惧另一人等。",
        parameters={
            "from_char": {
                "type": "string",
                "description": "关系主体角色的名字或role_id",
            },
            "to_char": {
                "type": "string",
                "description": "关系目标角色的名字或role_id",
            },
            "relation_type": {
                "type": "string",
                "enum": ["trust", "hostile", "subservient"],
                "description": "关系类型：trust(信任/结盟), hostile(敌对/防备), subservient(臣服/恐惧)",
            },
            "reason": {
                "type": "string",
                "description": "关系变化的剧情原因",
            },
        },
        handler=None,
    )


async def handle_transfer_points(target_char: str, amount: int, **kwargs) -> str:
    logger.info(f"LLM requested point transfer: {amount} pts to {target_char}")
    return json.dumps(
        {"status": "ok", "target": target_char, "amount": amount},
        ensure_ascii=False,
    )


async def handle_reveal_secret(secret_id: str, known_by: list[str], **kwargs) -> str:
    logger.info(f"LLM requested secret reveal: {secret_id} to {known_by}")
    return json.dumps(
        {"status": "ok", "secret_id": secret_id, "newly_known_by": known_by},
        ensure_ascii=False,
    )


async def handle_update_relation(
    from_char: str, to_char: str, relation_type: str, reason: str = "", **kwargs
) -> str:
    logger.info(f"LLM requested relation update: {from_char} -> {to_char} [{relation_type}]")
    return json.dumps(
        {
            "status": "ok",
            "from": from_char,
            "to": to_char,
            "relation_type": relation_type,
            "reason": reason,
        },
        ensure_ascii=False,
    )
