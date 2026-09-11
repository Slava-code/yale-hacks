"""Tests for the FastAPI server and SSE streaming."""

import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock

from backend.gatekeeper import PHIDetectionError
from backend.server import app, _load_graph_for_api, _run_pipeline


class TestHealthAndStaticEndpoints:
    def test_models_endpoint(self):
        client = TestClient(app)
        r = client.get("/api/models")
        assert r.status_code == 200
        data = r.json()
        assert "models" in data
        ids = [m["id"] for m in data["models"]]
        assert "claude" in ids
        assert "gpt4" in ids
        assert "gemini" in ids

    def test_graph_endpoint(self):
        client = TestClient(app)
        r = client.get("/api/graph")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) > 0
        # Nodes should have flat metadata (no PHI wrappers)
        node = data["nodes"][0]
        assert "id" in node
        assert "type" in node
        assert "color" in node
        assert "metadata" in node
        # metadata should be flat values, not {"value": ..., "phi": ...}
        for v in node["metadata"].values():
            assert not isinstance(v, dict)

    def test_graph_node_types(self):
        client = TestClient(app)
        r = client.get("/api/graph")
        data = r.json()
        types = {n["type"] for n in data["nodes"]}
        # Should have various clinical node types
        assert "patient" in types

    def test_pdf_endpoint_missing_file(self):
        client = TestClient(app)
        r = client.get("/api/pdf/nonexistent.pdf")
        assert r.status_code == 404

    def test_pdf_endpoint_rejects_traversal(self):
        """A filename escaping PDF_DIR must 404, not serve the file."""
        client = TestClient(app)
        r = client.get("/api/pdf/..%2F..%2Fpyproject.toml")
        assert r.status_code == 404


class TestPipelineFailsClosed:
    def test_phi_detection_failure_skips_cloud(self):
        """If de-identification fails, an error event is emitted and the cloud
        adapter is never called."""
        adapter = MagicMock()
        adapter.send_query = AsyncMock()
        gatekeeper = MagicMock()
        gatekeeper.deidentify_query = AsyncMock(
            side_effect=PHIDetectionError("local PHI detection model unavailable")
        )

        async def collect():
            return [event async for event in _run_pipeline("Tell me about John Smith", "claude")]

        with patch("backend.server._get_gatekeeper", return_value=gatekeeper), \
             patch("backend.server._get_adapter", return_value=adapter), \
             patch("backend.server._get_graph", return_value=MagicMock()):
            events = asyncio.run(collect())

        assert len(events) == 1
        event_type, data = events[0]
        assert event_type == "error"
        assert "not sent to the cloud" in data["content"]
        adapter.send_query.assert_not_called()


class TestQueryEndpointSSE:
    def test_query_returns_sse_stream(self):
        """Test that /api/query returns an SSE event stream with correct events."""
        client = TestClient(app)

        # Mock the gatekeeper and cloud adapter to avoid real LLM/API calls
        mock_deidentify = {
            "sanitized_query": "[PATIENT_1] has headaches",
            "token_mapping": None,  # will be replaced in mock
            "token_summary": {"PATIENT_1": "patient_name"},
            "patient_id": "patient_001",
        }

        with patch("backend.server._run_pipeline") as mock_pipeline:
            # Make the mock return SSE events
            async def fake_pipeline(message, model):
                events = [
                    ("deidentified_query", {
                        "type": "deidentified_query",
                        "content": "[PATIENT_1] has headaches",
                        "token_summary": {"PATIENT_1": "patient_name"},
                    }),
                    ("final_response", {
                        "type": "final_response",
                        "content": "John Smith has headaches. Consider further evaluation.",
                        "citations": [],
                        "model_used": "claude",
                        "gatekeeper_turns": 0,
                    }),
                ]
                for event_type, data in events:
                    yield event_type, data

            mock_pipeline.return_value = fake_pipeline("test", "claude")

            r = client.post(
                "/api/query",
                json={"message": "Tell me about John Smith", "model": "claude"},
            )
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]

    def test_query_requires_message(self):
        client = TestClient(app)
        r = client.post("/api/query", json={"model": "claude"})
        assert r.status_code == 422

    def test_query_requires_model(self):
        client = TestClient(app)
        r = client.post("/api/query", json={"message": "hello"})
        assert r.status_code == 422


class TestSSEEventFormat:
    def test_sse_event_format(self):
        """Verify SSE events match docs/interfaces.md §2 format."""
        from backend.server import _format_sse_event

        event = _format_sse_event("deidentified_query", {
            "type": "deidentified_query",
            "content": "test",
            "token_summary": {},
        })
        assert event.startswith("event: deidentified_query\n")
        assert "data: " in event
        assert event.endswith("\n\n")

        # Parse the data
        data_line = [l for l in event.split("\n") if l.startswith("data: ")][0]
        data = json.loads(data_line[6:])
        assert data["type"] == "deidentified_query"
