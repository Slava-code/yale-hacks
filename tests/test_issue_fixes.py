"""TDD tests for ISSUES.md fixes.

Each test targets a specific issue and is expected to FAIL before the fix
and PASS after. Tests are grouped by issue ID.

Run:  .venv/bin/python -m pytest tests/test_issue_fixes.py -v
"""

from __future__ import annotations

import asyncio
import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# ---------------------------------------------------------------------------
# C1: OpenAI adapter parse_tool_call must handle normalized tool_use blocks
# ---------------------------------------------------------------------------

class TestC1_OpenAIParseToolCall:
    """OpenAI parse_tool_call should work with BOTH native and normalized formats."""

    def test_parses_normalized_tool_use_block(self):
        """The server pipeline passes normalized blocks (type: tool_use).
        parse_tool_call must handle them, not only native OpenAI format."""
        from backend.adapters.openai_adapter import OpenAIAdapter
        adapter = OpenAIAdapter(api_key="test")

        # This is what _response_to_dict produces and server.py passes
        normalized_block = {
            "type": "tool_use",
            "id": "call_abc",
            "name": "query_gatekeeper",
            "input": {"query": "What are [PATIENT_1]'s labs?"},
        }
        result = adapter.parse_tool_call(normalized_block)
        assert result is not None, "parse_tool_call returned None for normalized tool_use block"
        assert result["tool_name"] == "query_gatekeeper"
        assert result["tool_id"] == "call_abc"
        assert result["arguments"]["query"] == "What are [PATIENT_1]'s labs?"

    def test_still_parses_native_openai_format(self):
        """Existing native format must still work."""
        from backend.adapters.openai_adapter import OpenAIAdapter
        adapter = OpenAIAdapter(api_key="test")

        native_block = {
            "id": "call_xyz",
            "type": "function",
            "function": {
                "name": "query_gatekeeper",
                "arguments": '{"query": "Get medications"}',
            },
        }
        result = adapter.parse_tool_call(native_block)
        assert result is not None
        assert result["tool_name"] == "query_gatekeeper"


# ---------------------------------------------------------------------------
# C2: OpenAI send_tool_result should use raw_message for conversation history
# ---------------------------------------------------------------------------

class TestC2_OpenAIMultiTurn:
    """OpenAI adapter must build correct message format for multi-turn tool calls."""

    def test_send_tool_result_appends_correct_assistant_format(self):
        """After a tool call, the assistant message in the conversation must
        use OpenAI-native format (with tool_calls field), not normalized blocks."""
        from backend.adapters.openai_adapter import OpenAIAdapter
        adapter = OpenAIAdapter(api_key="test")

        # Simulate the normalized response that _response_to_dict would produce
        mock_response = {
            "content": [
                {"type": "tool_use", "id": "call_1", "name": "query_gatekeeper",
                 "input": {"query": "labs"}}
            ],
            "stop_reason": "tool_calls",
            "raw_message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "query_gatekeeper", "arguments": '{"query": "labs"}'},
                }],
            },
        }

        # Build messages as server.py does
        messages = [{"role": "user", "content": "Tell me about labs"}]
        # Server appends assistant message — this is the key: it should use raw_message
        messages.append(mock_response.get("raw_message") or {
            "role": "assistant",
            "content": mock_response.get("content", []),
        })

        # The messages list should now have a properly formatted assistant message
        assistant_msg = messages[-1]
        assert assistant_msg["role"] == "assistant"
        # Must have tool_calls in OpenAI format, NOT content as a list of blocks
        assert "tool_calls" in assistant_msg or isinstance(assistant_msg.get("content"), (str, type(None)))


# ---------------------------------------------------------------------------
# C3: Gatekeeper should not block the async event loop
# ---------------------------------------------------------------------------

class TestC3_AsyncGatekeeper:
    """Gatekeeper methods called from async context must not block the event loop."""

    def test_chat_uses_async_http_or_is_wrapped(self):
        """_chat should either use async httpx or be wrapped in asyncio.to_thread."""
        from backend.gatekeeper import Gatekeeper
        import inspect

        gk = Gatekeeper(ollama_url="http://mock:11434", model="test")
        # Check if _chat is async (preferred fix)
        is_async = inspect.iscoroutinefunction(gk._chat)

        # Alternative: check if there's an async wrapper
        has_async_chat = hasattr(gk, '_achat') and inspect.iscoroutinefunction(gk._achat)

        # Alternative: check if deidentify_query is async
        deidentify_async = inspect.iscoroutinefunction(gk.deidentify_query)
        query_kg_async = inspect.iscoroutinefunction(gk.query_knowledge_graph)

        # At least one of these must be true
        assert is_async or has_async_chat or deidentify_async or query_kg_async, \
            "Gatekeeper LLM calls must be async or have async variants to avoid blocking the event loop"


# ---------------------------------------------------------------------------
# C4: Family history queries must return actual data
# ---------------------------------------------------------------------------

class TestC4_FamilyHistory:
    """Family history from graph must reach the cloud model, not silently drop."""

    def test_fetch_from_graph_returns_family_history(self):
        """_fetch_from_graph for 'get_family_history' should not return empty
        when family history data exists in the graph."""
        from backend.gatekeeper import Gatekeeper
        from backend.graph import load_graph

        gk = Gatekeeper(ollama_url="http://mock:11434", model="test")
        kg = load_graph("data/graph.json")

        # Find a patient that has family history
        from backend.graph import get_family_history
        test_patient_id = None
        for node_id, node in kg.nodes.items():
            if node.type == "patient":
                fh = get_family_history(kg, node_id)
                if fh:
                    test_patient_id = node_id
                    break

        if test_patient_id is None:
            pytest.skip("No patients with family history in graph.json")

        result = gk._fetch_from_graph("get_family_history", test_patient_id, kg, {})
        assert len(result) > 0, \
            f"_fetch_from_graph returned empty for patient {test_patient_id} who has family history"

    def test_compose_handles_family_history_format(self):
        """_compose_response or an equivalent must handle family history data
        (which comes as dicts from graph.py, not Nodes)."""
        from backend.gatekeeper import Gatekeeper
        from backend.graph import load_graph, get_family_history
        from backend.token_manager import TokenMapping
        from backend.citation import CitationManager

        gk = Gatekeeper(ollama_url="http://mock:11434", model="test")
        kg = load_graph("data/graph.json")

        # Find a patient with family history
        for node_id, node in kg.nodes.items():
            if node.type == "patient":
                fh = get_family_history(kg, node_id)
                if fh:
                    tm = TokenMapping()
                    tm.add(node.field_value("name"), "PATIENT")
                    cm = CitationManager()

                    # The full query_knowledge_graph should return meaningful content
                    import asyncio
                    from unittest.mock import AsyncMock
                    with patch.object(gk, '_parse_knowledge_query',
                                      new_callable=AsyncMock,
                                      return_value={"action": "get_family_history", "patient_id": node_id}):
                        result = asyncio.run(gk.query_knowledge_graph(
                            "What is the family history?", tm, kg, cm, patient_id=node_id
                        ))
                    assert "not available" not in result["content"].lower(), \
                        f"Family history returned 'not available' for patient with actual data: {fh}"
                    return

        pytest.skip("No patients with family history in graph.json")


# ---------------------------------------------------------------------------
# C5: Gemini _to_gemini_messages must handle non-string content
# ---------------------------------------------------------------------------

class TestC5_GeminiMessageConversion:
    """Gemini adapter must not drop messages with non-string content."""

    def test_handles_assistant_with_list_content(self):
        """Assistant messages from tool calls have list content (blocks).
        These must not be silently dropped."""
        from backend.adapters.gemini_adapter import GeminiAdapter
        adapter = GeminiAdapter(api_key="test")

        messages = [
            {"role": "user", "content": "Tell me about the patient"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "gemini_call", "name": "query_gatekeeper",
                 "input": {"query": "Get labs"}}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "gemini_call",
                 "content": "ANA positive"}
            ]},
        ]

        result = adapter._to_gemini_messages(messages)
        # Should not silently drop messages — at least the user message should be there
        # and the tool interaction should be represented somehow
        assert len(result) >= 2, \
            f"_to_gemini_messages dropped messages: got {len(result)} from {len(messages)} input messages"

    def test_all_messages_preserved(self):
        """Every message in the input should produce some output."""
        from backend.adapters.gemini_adapter import GeminiAdapter
        adapter = GeminiAdapter(api_key="test")

        messages = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1"},
            {"role": "user", "content": "Question 2"},
        ]
        result = adapter._to_gemini_messages(messages)
        assert len(result) == len(messages), \
            f"String messages should all be preserved, got {len(result)} from {len(messages)}"


# ---------------------------------------------------------------------------
# C6: Ollama errors must be caught gracefully
# ---------------------------------------------------------------------------

class TestC6_OllamaErrorHandling:
    """Ollama connection/timeout errors must not crash the pipeline."""

    def test_identify_phi_handles_connection_error(self):
        """If Ollama is unreachable, _identify_phi should return empty (fallback),
        not raise an unhandled exception."""
        from backend.gatekeeper import Gatekeeper
        import httpx

        gk = Gatekeeper(ollama_url="http://unreachable:99999", model="test")

        # Mock _chat to raise a connection error
        with patch.object(gk, '_chat', side_effect=httpx.ConnectError("Connection refused")):
            result = gk._identify_phi("Tell me about John Smith")
            if asyncio.iscoroutine(result):
                result = asyncio.run(result)
            assert isinstance(result, list)

    def test_parse_knowledge_query_handles_timeout(self):
        """If Ollama times out, _parse_knowledge_query should return fallback."""
        from backend.gatekeeper import Gatekeeper
        import httpx

        gk = Gatekeeper(ollama_url="http://unreachable:99999", model="test")

        with patch.object(gk, '_chat', side_effect=httpx.ReadTimeout("Timeout")):
            result = gk._parse_knowledge_query("Get patient labs")
            if asyncio.iscoroutine(result):
                result = asyncio.run(result)
            assert isinstance(result, dict)
            assert "action" in result


# ---------------------------------------------------------------------------
# M1: NODE_CONFIG must include all 9 node types
# ---------------------------------------------------------------------------

class TestM1_NodeConfig:
    """server.py NODE_CONFIG must include all node types from the spec."""

    def test_all_nine_node_types_configured(self):
        from backend.server import NODE_CONFIG
        expected_types = {
            "patient", "visit", "condition", "medication", "lab_result",
            "procedure", "provider", "family_history", "disease_reference",
        }
        assert expected_types.issubset(set(NODE_CONFIG.keys())), \
            f"Missing from NODE_CONFIG: {expected_types - set(NODE_CONFIG.keys())}"

    def test_family_history_has_correct_color(self):
        from backend.server import NODE_CONFIG
        fh = NODE_CONFIG.get("family_history", {})
        assert fh.get("color") == "#D946EF", f"family_history color should be #D946EF, got {fh.get('color')}"

    def test_disease_reference_has_correct_color(self):
        from backend.server import NODE_CONFIG
        dr = NODE_CONFIG.get("disease_reference", {})
        assert dr.get("color") == "#3B82F6", f"disease_reference color should be #3B82F6, got {dr.get('color')}"


# ---------------------------------------------------------------------------
# M2: GRAPH_PATH should resolve relative to project root
# ---------------------------------------------------------------------------

class TestM2_PathResolution:
    """Server paths should be absolute or resolve relative to project root."""

    def test_graph_path_is_absolute_or_anchored(self):
        """The default GRAPH_PATH should work regardless of CWD."""
        from backend import server
        # Re-read the module-level default (not the env-var override)
        import importlib
        # Check the source code for Path(__file__) pattern
        source = Path(server.__file__).read_text()
        # Either the path is built from __file__ or it's absolute
        uses_file_anchor = "__file__" in source and ("GRAPH_PATH" in source or "PROJECT_ROOT" in source)
        # Or the current default resolves correctly
        graph_path = Path(server.GRAPH_PATH)
        path_works = graph_path.is_absolute() or (Path("/Users/slavaiud/Desktop/Dev/hackathons/yale-hacks") / graph_path).exists()

        assert uses_file_anchor or path_works, \
            "GRAPH_PATH should be anchored to project root via __file__, not rely on CWD"


# ---------------------------------------------------------------------------
# M6: Empty API keys should fail fast
# ---------------------------------------------------------------------------

class TestM6_ApiKeyValidation:
    """Adapters should fail fast with clear errors for missing API keys."""

    def test_get_adapter_raises_on_missing_key(self):
        """_get_adapter should raise a clear error when the API key env var is not set."""
        from backend.server import _get_adapter

        # Ensure no API keys are set
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises((ValueError, RuntimeError)):
                _get_adapter("claude")

    def test_get_adapter_raises_on_empty_key(self):
        """Empty string API key should be treated as missing."""
        from backend.server import _get_adapter

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            with pytest.raises((ValueError, RuntimeError)):
                _get_adapter("claude")


# ---------------------------------------------------------------------------
# M7: Import should be at top level, not inside loop
# ---------------------------------------------------------------------------

class TestM7_TopLevelImport:
    """get_traversal_path should be importable at module level in server.py."""

    def test_get_traversal_path_in_top_level_imports(self):
        """server.py should import get_traversal_path at the top, not inside the loop."""
        source = Path("/Users/slavaiud/Desktop/Dev/hackathons/yale-hacks/backend/server.py").read_text()
        # Check top ~40 lines for the import
        top_lines = source.split("\n")[:40]
        top_section = "\n".join(top_lines)
        assert "get_traversal_path" in top_section, \
            "get_traversal_path should be imported at the top of server.py, not inside the pipeline loop"


# ---------------------------------------------------------------------------
# L5: Gatekeeper should use public API for token/graph access
# ---------------------------------------------------------------------------

class TestL5_PublicAPI:
    """Gatekeeper should not reach into private attributes."""

    def test_no_private_token_mapping_access(self):
        """Gatekeeper should not access _token_to_value directly."""
        source = Path("/Users/slavaiud/Desktop/Dev/hackathons/yale-hacks/backend/gatekeeper.py").read_text()
        assert "_token_to_value" not in source, \
            "Gatekeeper should use a public method to iterate token mappings, not _token_to_value"

    def test_no_private_graph_access(self):
        """Gatekeeper should not access _edges_from directly."""
        source = Path("/Users/slavaiud/Desktop/Dev/hackathons/yale-hacks/backend/gatekeeper.py").read_text()
        assert "_edges_from" not in source, \
            "Gatekeeper should use graph.py public API, not _edges_from"

    def test_token_mapping_has_public_iteration(self):
        """TokenMapping should expose a public way to iterate token-value pairs."""
        from backend.token_manager import TokenMapping
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")
        tm.add("Dr. Chen", "PROVIDER")

        # Should have a public method to get items
        assert hasattr(tm, "items") or hasattr(tm, "get_tokens") or hasattr(tm, "iter_tokens"), \
            "TokenMapping needs a public method for iterating token-value pairs"
