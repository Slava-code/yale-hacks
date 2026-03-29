"""Tests for the cloud model adapter layer."""

import pytest
from backend.adapters.base import CloudAdapter, CLOUD_SYSTEM_PROMPT, GATEKEEPER_TOOL
from backend.adapters.claude_adapter import ClaudeAdapter
from backend.adapters.openai_adapter import OpenAIAdapter
from backend.adapters.gemini_adapter import GeminiAdapter


class TestToolDefinition:
    def test_tool_has_required_fields(self):
        assert GATEKEEPER_TOOL["name"] == "query_gatekeeper"
        assert "description" in GATEKEEPER_TOOL
        assert "parameters" in GATEKEEPER_TOOL
        assert GATEKEEPER_TOOL["parameters"]["required"] == ["query"]

    def test_system_prompt_mentions_gatekeeper(self):
        assert "query_gatekeeper" in CLOUD_SYSTEM_PROMPT
        assert "PATIENT" in CLOUD_SYSTEM_PROMPT or "privacy" in CLOUD_SYSTEM_PROMPT.lower()


class TestClaudeAdapter:
    def test_formats_tool_for_anthropic(self):
        adapter = ClaudeAdapter(api_key="test-key")
        tools = adapter.format_tools()
        assert isinstance(tools, list)
        assert len(tools) == 2
        names = [t["name"] for t in tools]
        assert "query_gatekeeper" in names
        assert "web_search" in names
        assert "input_schema" in tools[0]

    def test_parse_tool_call_from_response(self):
        adapter = ClaudeAdapter(api_key="test-key")
        # Simulate an Anthropic tool_use response block
        mock_block = {
            "type": "tool_use",
            "id": "toolu_123",
            "name": "query_gatekeeper",
            "input": {"query": "What are [PATIENT_1]'s lab results?"},
        }
        result = adapter.parse_tool_call(mock_block)
        assert result["tool_name"] == "query_gatekeeper"
        assert result["tool_id"] == "toolu_123"
        assert result["arguments"]["query"] == "What are [PATIENT_1]'s lab results?"

    def test_parse_text_block_returns_none(self):
        adapter = ClaudeAdapter(api_key="test-key")
        mock_block = {"type": "text", "text": "Here is my analysis..."}
        result = adapter.parse_tool_call(mock_block)
        assert result is None

    def test_has_correct_model(self):
        adapter = ClaudeAdapter(api_key="test-key")
        assert "claude" in adapter.model.lower() or "sonnet" in adapter.model.lower()


class TestOpenAIAdapter:
    def test_formats_tool_for_openai(self):
        adapter = OpenAIAdapter(api_key="test-key")
        tools = adapter.format_tools()
        assert isinstance(tools, list)
        assert len(tools) == 2
        assert tools[0]["type"] == "function"
        names = [t["function"]["name"] for t in tools]
        assert "query_gatekeeper" in names
        assert "web_search" in names

    def test_parse_tool_call_from_response(self):
        adapter = OpenAIAdapter(api_key="test-key")
        # Simulate an OpenAI function call in a message
        mock_tool_call = {
            "id": "call_abc123",
            "type": "function",
            "function": {
                "name": "query_gatekeeper",
                "arguments": '{"query": "What are [PATIENT_1]\'s medications?"}',
            },
        }
        result = adapter.parse_tool_call(mock_tool_call)
        assert result["tool_name"] == "query_gatekeeper"
        assert result["tool_id"] == "call_abc123"
        assert "medications" in result["arguments"]["query"]

    def test_has_correct_model(self):
        adapter = OpenAIAdapter(api_key="test-key")
        assert "gpt" in adapter.model.lower()


class TestGeminiAdapter:
    def test_formats_tool_for_gemini(self):
        adapter = GeminiAdapter(api_key="test-key")
        tools = adapter.format_tools()
        assert isinstance(tools, list)
        assert "function_declarations" in tools[0]
        names = [d["name"] for d in tools[0]["function_declarations"]]
        assert "query_gatekeeper" in names
        assert "web_search" in names

    def test_parse_tool_call_from_response(self):
        adapter = GeminiAdapter(api_key="test-key")
        # Simulate a Gemini function call
        mock_part = {
            "function_call": {
                "name": "query_gatekeeper",
                "args": {"query": "What is [PATIENT_1]'s family history?"},
            }
        }
        result = adapter.parse_tool_call(mock_part)
        assert result["tool_name"] == "query_gatekeeper"
        assert "family history" in result["arguments"]["query"]

    def test_has_correct_model(self):
        adapter = GeminiAdapter(api_key="test-key")
        assert "gemini" in adapter.model.lower()


class TestAdapterInterface:
    """All adapters must implement the same interface."""

    @pytest.mark.parametrize("AdapterClass", [ClaudeAdapter, OpenAIAdapter, GeminiAdapter])
    def test_has_required_methods(self, AdapterClass):
        adapter = AdapterClass(api_key="test-key")
        assert hasattr(adapter, "format_tools")
        assert hasattr(adapter, "parse_tool_call")
        assert hasattr(adapter, "send_query")
        assert hasattr(adapter, "send_tool_result")
        assert hasattr(adapter, "model")
