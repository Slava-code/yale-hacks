"""
Claude (Anthropic) cloud adapter.

Spec: docs/backend.md §4.1 — Anthropic Messages API with tool use.
"""

from __future__ import annotations

import anthropic
from backend.adapters.base import CloudAdapter, CLOUD_SYSTEM_PROMPT, GATEKEEPER_TOOL, WEB_SEARCH_TOOL


class ClaudeAdapter(CloudAdapter):

    @property
    def model(self) -> str:
        return "claude-sonnet-4-20250514"

    def format_tools(self) -> list[dict]:
        """Anthropic uses 'input_schema' instead of 'parameters'."""
        tools = []
        for tool_def in [GATEKEEPER_TOOL, WEB_SEARCH_TOOL]:
            tools.append({
                "name": tool_def["name"],
                "description": tool_def["description"],
                "input_schema": tool_def["parameters"],
            })
        return tools

    def parse_tool_call(self, response_block: dict) -> dict | None:
        if response_block.get("type") != "tool_use":
            return None
        return {
            "tool_name": response_block["name"],
            "tool_id": response_block["id"],
            "arguments": response_block["input"],
        }

    async def send_query(self, messages: list[dict]) -> dict:
        client = anthropic.AsyncAnthropic(api_key=self.api_key, timeout=120.0)
        response = await client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=CLOUD_SYSTEM_PROMPT,
            tools=self.format_tools(),
            messages=messages,
        )
        return self._response_to_dict(response)

    async def send_tool_result(self, messages: list[dict], tool_id: str, result: str) -> dict:
        # Append the tool result to messages
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result,
                }
            ],
        })
        return await self.send_query(messages)

    def _response_to_dict(self, response) -> dict:
        """Normalize Anthropic response to a common format."""
        blocks = []
        for block in response.content:
            if block.type == "text":
                blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                blocks.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        return {
            "content": blocks,
            "stop_reason": response.stop_reason,
        }
