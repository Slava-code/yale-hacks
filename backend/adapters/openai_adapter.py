"""
OpenAI (GPT-4) cloud adapter.

Spec: docs/backend.md §4.1 — OpenAI Chat Completions with function calling.
"""

from __future__ import annotations

import json
import openai
from backend.adapters.base import CloudAdapter, CLOUD_SYSTEM_PROMPT, GATEKEEPER_TOOL


class OpenAIAdapter(CloudAdapter):

    @property
    def model(self) -> str:
        return "gpt-4o"

    def format_tool(self) -> dict:
        """OpenAI uses {"type": "function", "function": {...}} format."""
        return {
            "type": "function",
            "function": {
                "name": GATEKEEPER_TOOL["name"],
                "description": GATEKEEPER_TOOL["description"],
                "parameters": GATEKEEPER_TOOL["parameters"],
            },
        }

    def parse_tool_call(self, tool_call: dict) -> dict | None:
        if tool_call.get("type") != "function":
            return None
        return {
            "tool_name": tool_call["function"]["name"],
            "tool_id": tool_call["id"],
            "arguments": json.loads(tool_call["function"]["arguments"]),
        }

    async def send_query(self, messages: list[dict]) -> dict:
        client = openai.AsyncOpenAI(api_key=self.api_key)
        # Prepend system message
        full_messages = [{"role": "system", "content": CLOUD_SYSTEM_PROMPT}] + messages
        response = await client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            tools=[self.format_tool()],
            max_tokens=2048,
        )
        return self._response_to_dict(response)

    async def send_tool_result(self, messages: list[dict], tool_id: str, result: str) -> dict:
        messages.append({
            "role": "tool",
            "tool_call_id": tool_id,
            "content": result,
        })
        return await self.send_query(messages)

    def _response_to_dict(self, response) -> dict:
        """Normalize OpenAI response to a common format."""
        choice = response.choices[0]
        message = choice.message
        blocks = []

        if message.content:
            blocks.append({"type": "text", "text": message.content})

        if message.tool_calls:
            for tc in message.tool_calls:
                blocks.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json.loads(tc.function.arguments),
                })

        return {
            "content": blocks,
            "stop_reason": choice.finish_reason,
            "raw_message": {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in (message.tool_calls or [])
                ] or None,
            },
        }
