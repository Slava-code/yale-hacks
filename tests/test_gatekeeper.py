"""Tests for the gatekeeper module.

Tests marked @pytest.mark.gx10 require the GX10 with Ollama running.
All other tests run locally with mocked Ollama responses.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from backend.gatekeeper import Gatekeeper
from backend.graph import load_graph
from backend.token_manager import TokenMapping
from backend.citation import CitationManager

STUB_GRAPH_PATH = "data/stub/graph.json"


@pytest.fixture
def graph():
    return load_graph(STUB_GRAPH_PATH)


@pytest.fixture
def gatekeeper():
    return Gatekeeper(ollama_url="http://localhost:11434", model="qwen2.5:32b")


# --- deidentify_query tests (mocked LLM) ---

class TestDeidentifyQuery:
    def test_returns_sanitized_query_and_mapping(self, graph):
        """Mock the LLM to return known PHI spans, verify deterministic code works."""
        gk = Gatekeeper(ollama_url="http://mock:11434", model="test")

        # Simulate: LLM identifies "John Smith" as PATIENT and "Dr. Sarah Chen" as PROVIDER
        mock_phi_spans = [
            {"text": "John Smith", "type": "PATIENT"},
            {"text": "Dr. Sarah Chen", "type": "PROVIDER"},
        ]

        with patch.object(gk, '_identify_phi', return_value=mock_phi_spans):
            result = gk.deidentify_query(
                "Tell me about John Smith, Dr. Sarah Chen is his doctor",
                graph,
            )

        assert "[PATIENT_1]" in result["sanitized_query"]
        assert "[PROVIDER_1]" in result["sanitized_query"]
        assert "John Smith" not in result["sanitized_query"]
        assert "Dr. Sarah Chen" not in result["sanitized_query"]
        assert isinstance(result["token_mapping"], TokenMapping)
        assert "PATIENT_1" in result["token_summary"]

    def test_preserves_clinical_info(self, graph):
        gk = Gatekeeper(ollama_url="http://mock:11434", model="test")

        mock_phi_spans = [{"text": "John Smith", "type": "PATIENT"}]

        with patch.object(gk, '_identify_phi', return_value=mock_phi_spans):
            result = gk.deidentify_query(
                "John Smith has WBC 3.2 and recurring headaches for 8 months",
                graph,
            )

        assert "WBC 3.2" in result["sanitized_query"]
        assert "headaches" in result["sanitized_query"]
        assert "8 months" in result["sanitized_query"]


# --- query_knowledge_graph tests ---

class TestQueryKnowledgeGraph:
    def test_returns_redacted_response_with_refs(self, graph):
        gk = Gatekeeper(ollama_url="http://mock:11434", model="test")
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")
        cm = CitationManager()

        # Mock: LLM says "get labs for patient_001"
        mock_parsed = {"action": "get_patient_labs", "patient_id": "patient_001"}

        with patch.object(gk, '_parse_knowledge_query', return_value=mock_parsed):
            result = gk.query_knowledge_graph(
                "What are [PATIENT_1]'s lab results?",
                tm, graph, cm,
            )

        # Should have redacted content with REF tokens
        assert "[REF_" in result["content"]
        assert "John Smith" not in result["content"]
        # Should have accessed node IDs for graph traversal
        assert len(result["accessed_nodes"]) > 0
        assert "patient_001" in result["accessed_nodes"]
        # Should have refs added
        assert len(result["refs_added"]) > 0

    def test_patient_not_found(self, graph):
        gk = Gatekeeper(ollama_url="http://mock:11434", model="test")
        tm = TokenMapping()
        tm.add("Nobody", "PATIENT")
        cm = CitationManager()

        mock_parsed = {"action": "get_patient_labs", "patient_id": None}

        with patch.object(gk, '_parse_knowledge_query', return_value=mock_parsed):
            result = gk.query_knowledge_graph(
                "What are [PATIENT_1]'s lab results?",
                tm, graph, cm,
            )

        assert "not found" in result["content"].lower() or "not available" in result["content"].lower()


# --- rehydrate_response tests (pure deterministic) ---

class TestRehydrateResponse:
    def test_restores_names_and_resolves_refs(self):
        gk = Gatekeeper(ollama_url="http://mock:11434", model="test")
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")
        tm.add("Dr. Sarah Chen", "PROVIDER")

        cm = CitationManager()
        cm.add_ref("lab_report.pdf", 2, "Lab Report — Oct 2025, p.2")
        cm.add_ref("progress_note.pdf", 1, "Progress Note — Aug 2025, p.1")

        cloud_response = "[PATIENT_1]'s ANA is positive [REF_1]. [PROVIDER_1] should follow up [REF_2]."

        result = gk.rehydrate_response(cloud_response, tm, cm)

        assert "John Smith" in result["content"]
        assert "Dr. Sarah Chen" in result["content"]
        assert "[1]" in result["content"]
        assert "[2]" in result["content"]
        assert "[PATIENT_1]" not in result["content"]
        assert "[REF_1]" not in result["content"]
        assert len(result["citations"]) == 2
        assert result["citations"][0]["pdf"] == "lab_report.pdf"

    def test_destroys_mappings(self):
        gk = Gatekeeper(ollama_url="http://mock:11434", model="test")
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")
        cm = CitationManager()

        gk.rehydrate_response("[PATIENT_1] is fine.", tm, cm)

        # Token mapping should be destroyed
        assert tm.get_summary() == {}


# --- compose_graph_response tests (builds text from graph nodes) ---

class TestComposeGraphResponse:
    def test_composes_lab_results(self, graph):
        gk = Gatekeeper(ollama_url="http://mock:11434", model="test")
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")
        cm = CitationManager()

        from backend.graph import get_patient_labs
        labs = get_patient_labs(graph, "patient_001")
        result = gk._compose_response(labs, tm, cm)

        # Should mention lab values
        assert "ANA" in result["content"] or "ESR" in result["content"] or "CBC" in result["content"]
        # Should have REF tokens
        assert "[REF_" in result["content"]
        # Should not contain PHI
        assert "John Smith" not in result["content"]
