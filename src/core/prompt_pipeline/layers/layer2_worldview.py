from __future__ import annotations


def build_layer2(location_name: str, location_description: str, location_tags: list[str] | None = None) -> dict:
    """
    Layer 2: Worldview and Geography.
    Injects the current location's static description.
    """
    tags_str = ""
    if location_tags:
        tags_str = f"\n场景特征：{'、'.join(location_tags)}"

    content = f"""【世界观与地理信息】

## 高度育成高中
这是一所以"实力至上"为理念的精英高中。学生在校期间的个人点数、班级点数直接决定了生活质量和毕业后的出路。学校表面提供绝对的自由和优厚的待遇，但背后隐藏着严酷的竞争和淘汰机制。

## 当前所在位置
**{location_name}**
{location_description}{tags_str}
"""
    return {"role": "system", "content": content}
