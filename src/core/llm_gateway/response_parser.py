from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError


class LLMResponseSchema(BaseModel):
    """Expected JSON structure from LLM responses."""

    narrative: str = ""
    state_changes: dict[str, Any] = {}
    triggered_events: list[str] = []
    npc_reactions: dict[str, str] = {}


def parse_llm_response(raw: str) -> LLMResponseSchema:
    """Parse and validate LLM output. Falls back to treating entire output as narrative."""
    if not raw:
        return LLMResponseSchema(narrative="")

    cleaned = raw.strip()

    # Handle ```json ... ``` wrapping
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        content_lines = [l for l in lines if not l.startswith("```")]
        cleaned = "\n".join(content_lines).strip()

    # Try direct JSON parse
    try:
        data = json.loads(cleaned)
        return LLMResponseSchema(**data)
    except (json.JSONDecodeError, ValidationError):
        pass

    # Try to extract JSON from mixed text
    extracted = _extract_json(cleaned)
    if extracted:
        try:
            return LLMResponseSchema(**extracted)
        except ValidationError:
            pass

    # Fallback: entire output is narrative
    return LLMResponseSchema(narrative=raw)


def _extract_json(text: str) -> dict | None:
    """Extract JSON object from mixed text using brace matching."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        c = text[i]

        if escape_next:
            escape_next = False
            continue

        if c == "\\":
            escape_next = True
            continue

        if c == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None

    return None
