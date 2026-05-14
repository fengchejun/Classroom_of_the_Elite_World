from __future__ import annotations

RETURN_FORMAT_PROMPT = """【返回格式要求】

你必须始终以以下JSON格式返回（不要包含在```json代码块中）：

{
  "narrative": "你的叙事文本（第一人称，包含对话和环境描写）",
  "state_changes": {
    "player_location": "可选，玩家移动后的新位置ID",
    "time_advance_slots": 0,
    "new_events": [],
    "npc_status_updates": {}
  },
  "triggered_events": [],
  "npc_reactions": {}
}

字段说明：
- narrative: 必须包含。这是显示给玩家的叙述文本。
- state_changes: 可选。当玩家行为导致状态变化时填写。
  - player_location: 当玩家明确移动到新地点时填写地点ID
  - time_advance_slots: 当需要推进时间时填写（1-5）
  - new_events: 新触发的事件ID列表
- triggered_events: 剧情中触发了哪些事件
- npc_reactions: 在场NPC的具体反应，格式为 {"角色名": "反应描述"}

如果你需要调用工具来获取信息，先调用工具，不要在不确定时编造信息。
"""


def build_layer8() -> dict:
    """Layer 8: Return format specification."""
    return {"role": "system", "content": RETURN_FORMAT_PROMPT}
