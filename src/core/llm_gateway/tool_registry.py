from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    handler: Callable | None = None  # Async callable that takes **kwargs


class ToolRegistry:
    """Central registry for all LLM-callable tools."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        self._tools[definition.name] = definition
        logger.debug(f"Registered tool: {definition.name}")

    def get_definitions(self) -> list[dict]:
        """Get tool definitions in Anthropic format."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": {
                    "type": "object",
                    "properties": t.parameters,
                    "required": list(t.parameters.keys()),
                },
            }
            for t in self._tools.values()
        ]

    def get_openai_definitions(self) -> list[dict]:
        """Get tool definitions in OpenAI function calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {
                        "type": "object",
                        "properties": t.parameters,
                        "required": list(t.parameters.keys()),
                    },
                },
            }
            for t in self._tools.values()
        ]

    async def execute(self, name: str, arguments: dict) -> str:
        """Execute a tool by name. Returns the result as a JSON string."""
        tool = self._tools.get(name)
        if tool is None:
            return '{"error": "Unknown tool"}'
        if tool.handler is None:
            return '{"error": "Tool has no handler"}'
        try:
            result = await tool.handler(**arguments)
            return result
        except Exception as e:
            logger.error(f"Tool '{name}' execution failed: {e}")
            return f'{{"error": "{str(e)}"}}'


# Global registry instance
tool_registry = ToolRegistry()
