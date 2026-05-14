from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class SpotlightNPC:
    char_id: str
    name: str
    brief_status: str       # Visible state (e.g. "正在看书", "和旁边的人聊天")
    is_critical: bool = False  # Main cast or plot-relevant


class Spotlight:
    """
    Controls which NPCs enter the LLM's "field of view".
    Caps visible NPCs to prevent context overload.
    """

    def __init__(self, max_npcs: int = 3, base_count: int = 2):
        self.max_npcs = max_npcs
        self.base_count = base_count

    def select(
        self,
        present_npcs: list[dict],
        player_char_id: str | None = None,
        force_include: list[str] | None = None,
        critical_char_ids: set[str] | None = None,
    ) -> list[SpotlightNPC]:
        """
        Select which NPCs enter the spotlight.

        Selection logic:
        1. Always include force_include characters (e.g., event-critical NPCs)
        2. Prioritize critical_char_ids (main cast)
        3. Randomly fill remaining slots from present NPCs

        Returns 0..max_npcs spotlight entries.
        """
        if not present_npcs:
            return []

        selected: list[SpotlightNPC] = []
        remaining = [n for n in present_npcs if n["char_id"] != player_char_id]

        force = set(force_include or [])
        critical = set(critical_char_ids or [])

        # Pass 1: Force-include
        for npc in remaining[:]:
            if npc["char_id"] in force:
                selected.append(self._make_spotlight(npc, is_critical=True))
                remaining.remove(npc)
                force.discard(npc["char_id"])

        # Pass 2: Critical/important characters
        for npc in remaining[:]:
            if len(selected) >= self.max_npcs:
                break
            if npc["char_id"] in critical:
                selected.append(self._make_spotlight(npc, is_critical=True))
                remaining.remove(npc)

        # Pass 3: Random fill
        slots_left = self.max_npcs - len(selected)
        count_to_pick = min(slots_left, max(0, self.base_count - len(selected)))
        if remaining and count_to_pick > 0:
            picks = random.sample(remaining, min(count_to_pick, len(remaining)))
            for npc in picks:
                selected.append(self._make_spotlight(npc))

        # If we still have space and more NPCs exist, add up to max_npcs
        for npc in remaining:
            if len(selected) >= self.max_npcs:
                break
            if npc not in [s for s in selected if s.char_id == npc["char_id"]]:
                # Check if already selected
                already_in = any(s.char_id == npc["char_id"] for s in selected)
                if not already_in:
                    selected.append(self._make_spotlight(npc))

        return selected[: self.max_npcs]

    @staticmethod
    def _make_spotlight(npc: dict, is_critical: bool = False) -> SpotlightNPC:
        status_tags = npc.get("status_tags", [])
        brief = _derive_brief_status(status_tags)
        return SpotlightNPC(
            char_id=npc["char_id"],
            name=npc["name"],
            brief_status=brief,
            is_critical=is_critical,
        )


def _derive_brief_status(tags: list[str]) -> str:
    """Derive a brief visible status from tags."""
    tag_map = {
        "reading": "正在读书",
        "chatting": "正在与人交谈",
        "sleeping": "趴在桌上睡觉",
        "studying": "正在认真学习",
        "eating": "正在吃东西",
        "training": "正在训练",
        "wandering": "在附近徘徊",
        "normal": "看起来和平常一样",
        "injured": "看起来受了些伤",
        "absent": "不在此处",
        "nervous": "看起来有些紧张",
        "calm": "神情平静",
        "excited": "显得很兴奋",
    }
    for tag in tags:
        if tag in tag_map:
            return tag_map[tag]
    return "看起来和平常一样"
