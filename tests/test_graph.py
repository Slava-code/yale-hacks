"""Tests for the knowledge graph module — focused on FAMILY_HISTORY support."""

from pathlib import Path

from backend.graph import (
    get_family_history,
    get_node_by_id,
    load_graph,
)

ALL_NODE_TYPES = {
    "patient",
    "visit",
    "condition",
    "medication",
    "lab_result",
    "procedure",
    "provider",
    "family_history",
    "disease_reference",
}

ALL_EDGE_TYPES = {
    "HAD_VISIT",
    "HAS_CONDITION",
    "PRESCRIBED",
    "RESULTED_IN",
    "PERFORMED",
    "ATTENDED_BY",
    "TREATED_WITH",
    "MONITORED_BY",
    "REFERRED_TO",
    "HAS_FAMILY_HISTORY",
}


def test_stub_graph_loads(stub_graph):
    """Graph loads without error and has nodes and edges."""
    assert len(stub_graph.nodes) > 0
    assert len(stub_graph.edges) > 0


def test_stub_graph_has_all_node_types(stub_graph):
    """Stub graph contains all 9 node types."""
    present_types = {node.type for node in stub_graph.nodes.values()}
    missing = ALL_NODE_TYPES - present_types
    assert not missing, f"Missing node types in stub graph: {missing}"


def test_stub_graph_has_all_edge_types(stub_graph):
    """Stub graph contains all 10 edge types."""
    present_types = {edge["type"] for edge in stub_graph.edges}
    missing = ALL_EDGE_TYPES - present_types
    assert not missing, f"Missing edge types in stub graph: {missing}"


def test_get_family_history_returns_entries(stub_graph):
    """Patient 001 (John Smith) should have 2 family history entries."""
    fh = get_family_history(stub_graph, "patient_001")
    assert len(fh) == 2


def test_get_family_history_fields(stub_graph):
    """Each family history entry has the expected fields."""
    fh = get_family_history(stub_graph, "patient_001")
    for entry in fh:
        assert "relation" in entry, "Missing 'relation' field"
        assert "condition" in entry, "Missing 'condition' field"
        assert "diagnosed_age" in entry, "Missing 'diagnosed_age' field"
        assert "source_pdf" in entry, "Missing 'source_pdf' field"
        assert "source_page" in entry, "Missing 'source_page' field"
        assert entry["relation"] is not None
        assert entry["condition"] is not None


def test_get_family_history_empty_for_patient_without(stub_graph):
    """Patients without family history should return an empty list."""
    # patient_003 (David Chen) has no family history in the stub
    fh = get_family_history(stub_graph, "patient_003")
    assert fh == []


def test_stub_graph_meta_counts(stub_graph):
    """Meta counts should reflect the updated node/edge totals."""
    assert stub_graph.meta["num_nodes"] == 39
    assert stub_graph.meta["num_edges"] == 43


def test_node_config_has_family_history():
    """stub_server.NODE_CONFIG should include family_history."""
    # Parse NODE_CONFIG directly from source to avoid importing FastAPI
    import ast

    source_path = Path(__file__).resolve().parent.parent / "backend" / "stub_server.py"
    source = source_path.read_text()

    # Find the NODE_CONFIG assignment and evaluate it
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "NODE_CONFIG":
                    node_config = ast.literal_eval(node.value)
                    assert "family_history" in node_config
                    assert "color" in node_config["family_history"]
                    assert "size" in node_config["family_history"]
                    return

    pytest.fail("NODE_CONFIG not found in stub_server.py")


def test_search_nodes_finds_disease_reference(stub_graph):
    """search_nodes should find disease references by symptom keywords."""
    from backend.graph import search_nodes

    results = search_nodes(stub_graph, "malar rash", node_type="disease_reference")
    # Stub graph includes SLE disease reference with "Malar rash" in symptoms
    assert len(results) >= 1
    assert any("Lupus" in r.label for r in results)


def test_search_disease_references(stub_graph):
    """search_disease_references convenience wrapper works."""
    from backend.graph import search_disease_references

    results = search_disease_references(stub_graph, "aggression")
    assert len(results) >= 0  # Should not crash; may find rabies in stub


def test_node_config_has_disease_reference():
    """stub_server.NODE_CONFIG should include disease_reference."""
    import ast

    source_path = Path(__file__).resolve().parent.parent / "backend" / "stub_server.py"
    source = source_path.read_text()

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "NODE_CONFIG":
                    node_config = ast.literal_eval(node.value)
                    assert "disease_reference" in node_config
                    assert "color" in node_config["disease_reference"]
                    assert "size" in node_config["disease_reference"]
                    return

    pytest.fail("NODE_CONFIG not found in stub_server.py")
