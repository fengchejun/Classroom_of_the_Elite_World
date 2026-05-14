from __future__ import annotations

from dataclasses import dataclass, field

from src.core.prompt_pipeline.layers.layer1_global import build_layer1
from src.core.prompt_pipeline.layers.layer2_worldview import build_layer2
from src.core.prompt_pipeline.layers.layer3_history import build_layer3
from src.core.prompt_pipeline.layers.layer4_dynamic import build_layer4
from src.core.prompt_pipeline.layers.layer5_state import build_layer5
from src.core.prompt_pipeline.layers.layer6_tool import build_layer6
from src.core.prompt_pipeline.layers.layer7_user import build_layer7
from src.core.prompt_pipeline.layers.layer8_format import build_layer8
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AssembledContext:
    """The fully assembled context ready for LLM API call."""
    messages: list[dict]
    system_prompt: str        # Combined system prompt for APIs that use a separate system param


@dataclass
class AssemblyInput:
    """All inputs needed to assemble a complete prompt."""
    # Layer 2
    location_name: str
    location_description: str
    location_tags: list[str] = field(default_factory=list)

    # Layer 3
    recent_dialogues: list[dict] = field(default_factory=list)
    story_summaries: list[str] = field(default_factory=list)

    # Layer 4
    active_events: list[dict] | None = None
    rules_appendix: str | None = None
    foreshadowing_prompts: list[str] | None = None

    # Layer 5
    game_date: str = "2024-04-01"
    time_slot: str = "morning"
    spotlight_npcs: list[dict] = field(default_factory=list)
    player_stats: dict | None = None

    # Layer 6
    tool_results: list[dict] | None = None

    # Layer 7
    user_input: str = ""
    choice_id: str | None = None


class PromptAssembler:
    """Assembles the 8-layer prompt pipeline for LLM consumption."""

    async def assemble(self, inp: AssemblyInput) -> AssembledContext:
        """
        Build the complete messages array following the 8-layer order:

        L1: Global system constraints
        L2: Worldview and geography
        L3: Historical dialogue review
        L4: Dynamic events and rules (on-demand)
        L5: Real-time state (time + spotlight NPCs)
        L6: Tool feedback (dynamic insertion)
        L7: Player input
        L8: Return format specification

        Returns AssembledContext with both messages array and combined system prompt.
        """
        messages: list[dict] = []

        # ---- Layer 1: Global system constraints ----
        l1 = build_layer1()
        system_parts = [l1["content"]]

        # ---- Layer 2: Worldview and geography ----
        l2 = build_layer2(
            location_name=inp.location_name,
            location_description=inp.location_description,
            location_tags=inp.location_tags,
        )
        system_parts.append(l2["content"])

        # Combine L1 + L2 as the system prompt
        combined_system = "\n\n---\n\n".join(system_parts)
        messages.append({"role": "system", "content": combined_system})

        # ---- Layer 3: Historical dialogue review ----
        l3 = build_layer3(
            recent_dialogues=inp.recent_dialogues,
            story_summaries=inp.story_summaries,
        )
        if l3["content"] != "【无历史记录】":
            messages.append(l3)

        # ---- Layer 4: Dynamic events and rules (on-demand) ----
        l4 = build_layer4(
            active_events=inp.active_events,
            rules_appendix=inp.rules_appendix,
            foreshadowing_prompts=inp.foreshadowing_prompts,
        )
        if l4 is not None:
            messages.append(l4)

        # ---- Layer 5: Real-time state ----
        l5 = build_layer5(
            game_date=inp.game_date,
            time_slot=inp.time_slot,
            spotlight_npcs=inp.spotlight_npcs,
            player_stats=inp.player_stats,
        )
        messages.append(l5)

        # ---- Layer 6: Tool feedback (dynamic) ----
        l6_msgs = build_layer6(inp.tool_results)
        if l6_msgs:
            messages.extend(l6_msgs)

        # ---- Layer 7: Player input ----
        l7 = build_layer7(inp.user_input, inp.choice_id)
        messages.append(l7)

        # ---- Layer 8: Return format specification ----
        l8 = build_layer8()
        messages.append(l8)

        logger.debug(f"Assembled {len(messages)} messages for LLM")

        return AssembledContext(
            messages=messages,
            system_prompt=combined_system,
        )

    async def assemble_forecast(
        self,
        game_date: str,
        time_slot: str,
        active_events: list[dict] | None = None,
        npc_states: list[dict] | None = None,
    ) -> list[dict]:
        """
        Build a specialized prompt for the AI Forecaster system.
        Asks the LLM to generate 2 small side events for the next 1-3 days.
        """
        npc_summary = ""
        if npc_states:
            npc_lines = []
            for npc in npc_states:
                npc_lines.append(f"- {npc['name']}：位置{npc.get('location', '?')}，状态{npc.get('tags', [])}")
            npc_summary = "\n".join(npc_lines)

        active_summary = ""
        if active_events:
            active_summary = "\n".join([f"- {ev['name']}（{ev.get('phase', '?')}）" for ev in active_events])

        forecast_prompt = f"""你是一个AI剧情导演。请根据当前游戏状态，预先生成2个可能在接下来1-3天内发生的小型支线事件。

当前日期：{game_date} {time_slot}

正在发生的事件：
{active_summary or '（无）'}

主要角色状态：
{npc_summary or '（无特殊状态）'}

请生成2个事件，每个事件必须包含：
1. name: 事件名称
2. trigger_location: 触发地点ID（玩家必须在此地点才能触发）
3. trigger_date_start / trigger_date_end: 触发日期范围
4. ai_setup_prompt: 事件触发时的LLM叙事提示（含冲突设置和悬停点）
5. options: 至少2个选项，每个包含 id, text, target_event, stat_changes

格式为JSON数组：
[
  {{"name": "...", "trigger_location": "...", "trigger_date_start": "...", "trigger_date_end": "...", "ai_setup_prompt": "...", "options": [...]}},
  ...
]
"""
        return [
            {"role": "system", "content": "你是剧情生成引擎，只输出要求的JSON格式，不要添加额外说明。"},
            {"role": "user", "content": forecast_prompt},
        ]
