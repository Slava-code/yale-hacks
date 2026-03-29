"""
Gemini (Google) cloud adapter.

Spec: docs/backend.md §4.1 — Google GenAI with function declarations.
"""

from __future__ import annotations

import google.generativeai as genai
from backend.adapters.base import CloudAdapter, CLOUD_SYSTEM_PROMPT, GATEKEEPER_TOOL


class GeminiAdapter(CloudAdapter):

    @property
    def model(self) -> str:
        return "gemini-2.5-flash"

    def format_tool(self) -> dict:
        """Gemini uses function_declarations format."""
        return {
            "function_declarations": [
                {
                    "name": GATEKEEPER_TOOL["name"],
                    "description": GATEKEEPER_TOOL["description"],
                    "parameters": GATEKEEPER_TOOL["parameters"],
                }
            ]
        }

    def parse_tool_call(self, part: dict) -> dict | None:
        # Handle normalized format from _response_to_dict
        if part.get("type") == "tool_use":
            return {
                "tool_name": part["name"],
                "tool_id": part.get("id", "gemini_call"),
                "arguments": part.get("input", {}),
            }
        # Handle raw Gemini format
        fc = part.get("function_call")
        if not fc:
            return None
        return {
            "tool_name": fc["name"],
            "tool_id": fc.get("id", "gemini_call"),
            "arguments": dict(fc.get("args", {})),
        }

    async def send_query(self, messages: list[dict]) -> dict:
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            self.model,
            system_instruction=CLOUD_SYSTEM_PROMPT,
            tools=[self.format_tool()],
        )
        # Convert messages to Gemini format
        gemini_history = self._to_gemini_messages(messages[:-1])
        last_msg = messages[-1]["content"] if messages else ""

        chat = model.start_chat(history=gemini_history)
        # Force tool use on first message so Gemini queries the gatekeeper
        tool_config = None
        if len(messages) == 1:
            tool_config = {"function_calling_config": {"mode": "ANY"}}
        response = await chat.send_message_async(last_msg, tool_config=tool_config)
        return self._response_to_dict(response)

    async def send_tool_result(self, messages: list[dict], tool_id: str, result: str) -> dict:
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            self.model,
            system_instruction=CLOUD_SYSTEM_PROMPT,
            tools=[self.format_tool()],
        )
        gemini_history = self._to_gemini_messages(messages)
        chat = model.start_chat(history=gemini_history)

        # Send function response
        response = await chat.send_message_async(
            genai.protos.Content(
                parts=[
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name="query_gatekeeper",
                            response={"result": result},
                        )
                    )
                ]
            )
        )
        return self._response_to_dict(response)

    def _to_gemini_messages(self, messages: list[dict]) -> list:
        """Convert standard messages to Gemini Content format."""
        history = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            content = msg.get("content", "")
            if isinstance(content, str):
                history.append({"role": role, "parts": [content]})
        return history

    def _response_to_dict(self, response) -> dict:
        """Normalize Gemini response to common format."""
        blocks = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call.name:
                    blocks.append({
                        "type": "tool_use",
                        "id": "gemini_call",
                        "name": part.function_call.name,
                        "input": dict(part.function_call.args),
                    })
                elif hasattr(part, "text") and part.text:
                    blocks.append({"type": "text", "text": part.text})

        stop = "tool_calls" if any(b["type"] == "tool_use" for b in blocks) else "end_turn"
        return {"content": blocks, "stop_reason": stop}
