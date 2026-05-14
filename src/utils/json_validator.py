from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError


class LLMResponseSchema(BaseModel):
    """Expected JSON structure from LLM responses."""

    narrative: str  # Main narrative text (shown to player)
    state_changes: dict[str, Any] = {}  # State mutations
    triggered_events: list[str] = []  # Events triggered by this response
    npc_reactions: dict[str, str] = {}  # NPC-specific reactions: {char_id: text}


def parse_llm_response(raw: str) -> LLMResponseSchema:
    """Parse and validate LLM JSON output. Falls back to plain text if JSON is malformed."""
    try:
        # LLM might wrap JSON in ```json blocks
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            # Remove first (```json) and last (```) lines
            content_lines = [l for l in lines if not l.startswith("```")]
            raw = "\n".join(content_lines)
        data = json.loads(raw)
        return LLMResponseSchema(**data)
    except (json.JSONDecodeError, ValidationError):
        # Fallback: treat entire output as narrative
        return LLMResponseSchema(narrative=raw)


def extract_json_from_text(text: str) -> dict | None:
    """Attempt to extract a JSON object from mixed text. Returns None if no JSON found."""
    import re

    # Try to find JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None
