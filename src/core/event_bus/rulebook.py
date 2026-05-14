from __future__ import annotations

import os
from pathlib import Path


class RulebookManager:
    """Manages loading and formatting of exam rule appendices."""

    RULEBOOK_DIR = Path(__file__).parent.parent.parent / "config" / "data" / "rulebooks"

    # Strong warning appended to all rule injections
    NARRATIVE_CONSTRAINT = (
        "⚠️ 绝对约束：以下规则仅供你推演NPC的博弈逻辑使用，"
        "严禁以任何形式向玩家机械复述或原文背诵这些规则。"
        "你应当通过NPC的对话、行为和环境描写自然地让玩家感受到规则的存在。"
    )

    def load_rulebook(self, keyword: str) -> str | None:
        """Load a specific rulebook by keyword."""
        file_path = self.RULEBOOK_DIR / f"{keyword}.txt"
        if not file_path.exists():
            return None
        content = file_path.read_text(encoding="utf-8")
        return f"{self.NARRATIVE_CONSTRAINT}\n\n---\n{content}\n---"

    def get_rule_context(self, keyword: str) -> dict | None:
        """Get structured rule context for LLM injection."""
        content = self.load_rulebook(keyword)
        if content is None:
            return None
        return {
            "rule_keyword": keyword,
            "content": content,
            "role": "system_constraint",
        }

    def list_available_rulebooks(self) -> list[str]:
        """List all available rulebook files."""
        if not self.RULEBOOK_DIR.exists():
            return []
        return [
            f.stem
            for f in self.RULEBOOK_DIR.glob("*.txt")
            if f.is_file()
        ]

    @classmethod
    def get_constraint_text(cls) -> str:
        return cls.NARRATIVE_CONSTRAINT
