from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

from src.config.settings import settings
from src.core.llm_gateway.response_parser import parse_llm_response
from src.core.llm_gateway.tool_registry import ToolRegistry, tool_registry
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LLMResponse:
    narrative: str
    state_changes: dict
    triggered_events: list[str]
    npc_reactions: dict[str, str]
    raw_messages: list[dict] = field(default_factory=list)


class LLMGateway:
    """Gateway for LLM interaction using DeepSeek API (OpenAI-compatible)."""

    def __init__(self, tools: ToolRegistry | None = None):
        self.tools = tools or tool_registry
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url
        self.model = settings.llm_model
        self.max_tokens = settings.llm_max_tokens
        self.temperature = settings.llm_temperature

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[dict],
        system: str = "",
    ) -> LLMResponse:
        """
        Main chat interface with tool calling loop using DeepSeek API.
        """
        # Build messages in OpenAI format
        openai_messages = self._build_openai_messages(messages, system)
        return await self._send_with_tool_loop(openai_messages, max_iterations=5)

    async def generate_forecast(self, messages: list[dict]) -> list[dict]:
        """Generate forecast events using DeepSeek."""
        forecast_system = next(
            (m["content"] for m in messages if m.get("role") == "system"),
            "",
        )
        openai_msgs = self._build_openai_messages(messages, forecast_system)

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers,
                    json={
                        "model": settings.forecaster_model,
                        "messages": openai_msgs,
                        "max_tokens": 1024,
                        "temperature": 0.9,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                result = json.loads(content.strip())
                return result if isinstance(result, list) else [result]
            except Exception as e:
                logger.error(f"Forecast generation failed: {e}")
                return []

    async def _send_with_tool_loop(
        self,
        messages: list[dict],
        max_iterations: int = 5,
    ) -> LLMResponse:
        """Send messages with tool calling loop."""
        current_messages = list(messages)
        tool_defs = self.tools.get_openai_definitions()

        async with httpx.AsyncClient(timeout=120.0) as client:
            for iteration in range(max_iterations):
                payload = {
                    "model": self.model,
                    "messages": current_messages,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                }
                if tool_defs:
                    payload["tools"] = tool_defs
                    payload["tool_choice"] = "auto"

                try:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers,
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except httpx.HTTPError as e:
                    logger.error(f"DeepSeek API error: {e}")
                    return LLMResponse(
                        narrative=f"[系统错误：AI响应失败]",
                        state_changes={},
                        triggered_events=[],
                        npc_reactions={},
                    )

                choice = data["choices"][0]
                msg = choice["message"]

                # Check for tool calls
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    # Add assistant message
                    current_messages.append({
                        "role": "assistant",
                        "content": msg.get("content") or "",
                        "tool_calls": tool_calls,
                    })

                    # Execute tools
                    for tc in tool_calls:
                        func_name = tc["function"]["name"]
                        try:
                            func_args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            func_args = {}

                        result_str = await self.tools.execute(func_name, func_args)

                        current_messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result_str,
                        })

                    logger.debug(
                        f"Tool call iteration {iteration + 1}: "
                        f"{[tc['function']['name'] for tc in tool_calls]}"
                    )
                    continue

                # No tool calls — final response
                text_content = msg.get("content", "")
                parsed = parse_llm_response(text_content)
                return LLMResponse(
                    narrative=parsed.narrative,
                    state_changes=parsed.state_changes,
                    triggered_events=parsed.triggered_events,
                    npc_reactions=parsed.npc_reactions,
                )

        # Max iterations reached
        logger.warning("Max tool call iterations reached")
        return LLMResponse(
            narrative="[系统提示：AI处理达到最大轮次，请继续你的行动。]",
            state_changes={},
            triggered_events=[],
            npc_reactions={},
        )

    def _build_openai_messages(
        self, messages: list[dict], system: str = ""
    ) -> list[dict]:
        """Convert our internal message format to OpenAI format."""
        converted = []

        if system:
            converted.append({"role": "system", "content": system})

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # Merge system messages into one
                if converted and converted[0]["role"] == "system":
                    converted[0]["content"] += "\n\n" + str(content)
                else:
                    converted.insert(0, {"role": "system", "content": str(content)})
            elif role in ("user", "assistant", "tool"):
                converted.append({"role": role, "content": str(content)})
            else:
                converted.append({"role": "user", "content": str(content)})

        return converted
