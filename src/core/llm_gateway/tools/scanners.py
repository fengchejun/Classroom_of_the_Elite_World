from __future__ import annotations

import json

from src.core.llm_gateway.tool_registry import ToolDefinition
from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_character_info_definition() -> ToolDefinition:
    return ToolDefinition(
        name="get_character_info",
        description="查询某个角色的详细信息，包括公开形象和（若玩家已解锁）隐藏秘密。当需要深入了解某个NPC、或NPC在剧情中出现时调用。",
        parameters={
            "char_name": {
                "type": "string",
                "description": "要查询的角色名字或role_id",
            },
        },
        handler=None,
    )


def query_social_network_definition() -> ToolDefinition:
    return ToolDefinition(
        name="query_social_network",
        description="查询某个角色的社会关系网，包括他们信任的人、敌对的人以及畏惧的人。用于理解角色之间的派系关系和行为动机。",
        parameters={
            "char_name": {
                "type": "string",
                "description": "要查询的角色名字或role_id",
            },
        },
        handler=None,
    )


def check_exam_rules_definition() -> ToolDefinition:
    return ToolDefinition(
        name="check_exam_rules",
        description="查阅当前激活的特别考试的具体规则细节。仅在玩家主动询问或讨论考试规则时调用。返回的规则仅供你推演NPC的博弈逻辑，严禁机械复述给玩家。",
        parameters={
            "keyword": {
                "type": "string",
                "description": "要查询的规则关键词，如'midterm_exam', 'uninhabited_island'等",
            },
        },
        handler=None,
    )


async def handle_get_character_info(char_name: str, **kwargs) -> str:
    logger.info(f"LLM requested character info: {char_name}")
    # Placeholder - actual implementation wired at runtime
    return json.dumps({"status": "pending", "char_name": char_name}, ensure_ascii=False)


async def handle_query_social_network(char_name: str, **kwargs) -> str:
    logger.info(f"LLM requested social network: {char_name}")
    return json.dumps({"status": "pending", "char_name": char_name}, ensure_ascii=False)


async def handle_check_exam_rules(keyword: str, **kwargs) -> str:
    logger.info(f"LLM requested exam rules: {keyword}")
    return json.dumps({"status": "pending", "keyword": keyword}, ensure_ascii=False)
