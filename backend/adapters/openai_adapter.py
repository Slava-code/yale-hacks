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
        # Native OpenAI format: {"type": "function", "function": {...}, "id": ...}
        if tool_call.get("type") == "function":
            return {
                "tool_name": tool_call["function"]["name"],
                "tool_id": tool_call["id"],
                "arguments": json.loads(tool_call["function"]["arguments"]),
            }
        # Normalized format from _response_to_dict: {"type": "tool_use", "id": ..., "name": ..., "input": {...}}
        if tool_call.get("type") == "tool_use":
            return {
                "tool_name": tool_call["name"],
                "tool_id": tool_call["id"],
                "arguments": tool_call["input"],
            }
        return None

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
        # Fix C2: If the last message is an assistant message with normalized block
        # content (list of dicts with "type": "tool_use"), convert it to OpenAI
        # native format with a "tool_calls" field.
        if messages and messages[-1].get("role") == "assistant":
            last = messages[-1]
            content = last.get("content")
            if isinstance(content, list):
                text_parts = []
                tool_calls = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block["input"]),
                            },
                        })
                    elif isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                # Replace the last message with OpenAI-native format
                native_msg: dict = {"role": "assistant", "content": "".join(text_parts) or None}
                if tool_calls:
                    native_msg["tool_calls"] = tool_calls
                messages[-1] = native_msg

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
