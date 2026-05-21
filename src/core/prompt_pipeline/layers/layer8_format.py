from __future__ import annotations

RETURN_FORMAT_PROMPT = """【返回格式要求】

你必须始终以以下JSON格式返回（不要包含在```json代码块中）：

{
  "narrative": "你的叙事文本（第一人称，包含对话和环境描写）",
  "choices": [{"id": "1", "text": "选项文本"}, ...]
}

字段说明：
- narrative: 必须包含。这是显示给玩家的叙述文本。
- choices: 引导下一步行动的选项列表，通常2-4个。

注意：你只需要返回 narrative 和 choices。时间推进、位置变化、点数变动、人际关系变化等状态变更由另一个专门的系统自动处理，你无需在JSON中包含state_changes字段。

如果你需要调用工具来获取信息，先调用工具，不要在不确定时编造信息。
"""


def build_layer8() -> dict:
    """Layer 8: Return format specification."""
    return {"role": "system", "content": RETURN_FORMAT_PROMPT}
