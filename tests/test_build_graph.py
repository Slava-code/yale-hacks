"""Tests for the deterministic graph builder — scripts/build_graph.py."""

import json
from datetime import datetime
from pathlib import Path

from backend.graph import load_graph, get_patient


ALL_NODE_TYPES = {
    "patient", "visit", "condition", "medication",
    "lab_result", "procedure", "provider", "family_history",
    "disease_reference",
}

ALL_EDGE_TYPES = {
    "HAD_VISIT", "HAS_CONDITION", "PRESCRIBED", "RESULTED_IN",
    "PERFORMED", "ATTENDED_BY", "TREATED_WITH", "MONITORED_BY",
    "REFERRED_TO", "HAS_FAMILY_HISTORY",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nodes_of_type(graph, node_type):
    return [n for n in graph["nodes"].values() if n["type"] == node_type]


def _edges_of_type(graph, edge_type):
    return [e for e in graph["edges"] if e["type"] == edge_type]


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_returns_valid_structure(built_graph):
    """Output has meta, nodes (dict), and edges (list)."""
    assert "meta" in built_graph
    assert isinstance(built_graph["nodes"], dict)
    assert isinstance(built_graph["edges"], list)


def test_meta_counts(built_graph):
    """Meta counts match actual node/edge counts."""
    meta = built_graph["meta"]
    assert meta["num_patients"] == 2
    assert meta["num_nodes"] == len(built_graph["nodes"])
    assert meta["num_edges"] == len(built_graph["edges"])
    assert meta["num_nodes"] == 132
    assert meta["num_edges"] == 165
    # generated_at is a valid ISO timestamp
    datetime.fromisoformat(meta["generated_at"].replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Node counts and fields
# ---------------------------------------------------------------------------

def test_patient_nodes(built_graph):
    """2 patient nodes with correct PHI tagging."""
    patients = _nodes_of_type(built_graph, "patient")
    assert len(patients) == 2
    for p in patients:
        fields = p["fields"]
        assert fields["name"]["phi"] is True
        assert fields["mrn"]["phi"] is True
        assert fields["age"]["phi"] is False
        assert fields["sex"]["phi"] is False
        assert fields["summary"]["phi"] is False
        assert p.get("source_pdf") is not None


def test_visit_nodes(built_graph):
    """31 visit nodes with correct fields and PHI tagging."""
    visits = _nodes_of_type(built_graph, "visit")
    assert len(visits) == 31
    for v in visits:
        fields = v["fields"]
        assert fields["date"]["phi"] is True
        assert fields["visit_type"]["phi"] is False
        assert fields["chief_complaint"]["phi"] is False
        assert fields["attending_provider"]["phi"] is True
        assert fields["notes"]["phi"] is False
        assert v.get("source_pdf") is not None


def test_condition_nodes(built_graph):
    """8 condition nodes with correct fields."""
    conditions = _nodes_of_type(built_graph, "condition")
    assert len(conditions) == 8
    for c in conditions:
        fields = c["fields"]
        assert fields["name"]["phi"] is False
        assert fields["icd_code"]["phi"] is False
        assert fields["status"]["phi"] is False


def test_medication_nodes(built_graph):
    """11 medication nodes with correct fields and PHI tagging."""
    meds = _nodes_of_type(built_graph, "medication")
    assert len(meds) == 11
    for m in meds:
        fields = m["fields"]
        assert fields["name"]["phi"] is False
        assert fields["dosage"]["phi"] is False
        assert fields["frequency"]["phi"] is False
        assert fields["prescribing_provider"]["phi"] is True
        assert fields["start_date"]["phi"] is True
        assert fields["status"]["phi"] is False


def test_lab_result_nodes(built_graph):
    """48 lab_result nodes with source provenance."""
    labs = _nodes_of_type(built_graph, "lab_result")
    assert len(labs) == 48
    for lab in labs:
        fields = lab["fields"]
        assert "test_name" in fields
        assert "value" in fields
        assert "unit" in fields
        assert "reference_range" in fields
        assert "flag" in fields
        assert fields["date"]["phi"] is True
        assert lab.get("source_pdf") is not None
        assert lab.get("source_page") is not None


def test_procedure_nodes(built_graph):
    """4 procedure nodes."""
    procs = _nodes_of_type(built_graph, "procedure")
    assert len(procs) == 4
    for p in procs:
        fields = p["fields"]
        assert fields["name"]["phi"] is False
        assert fields["date"]["phi"] is True
        assert fields["provider"]["phi"] is True
        assert fields["outcome"]["phi"] is False


def test_provider_nodes(built_graph):
    """9 provider nodes with correct PHI tagging."""
    providers = _nodes_of_type(built_graph, "provider")
    assert len(providers) == 9
    for p in providers:
        fields = p["fields"]
        assert fields["name"]["phi"] is True
        assert fields["role"]["phi"] is False
        assert fields["department"]["phi"] is False


def test_family_history_nodes(built_graph):
    """3 family_history nodes."""
    fh = _nodes_of_type(built_graph, "family_history")
    assert len(fh) == 3
    for f in fh:
        fields = f["fields"]
        assert "relation" in fields
        assert "condition" in fields


# ---------------------------------------------------------------------------
# Node and edge type coverage
# ---------------------------------------------------------------------------

def test_all_node_types_present(built_graph):
    """All 9 node types exist."""
    present = {n["type"] for n in built_graph["nodes"].values()}
    missing = ALL_NODE_TYPES - present
    assert not missing, f"Missing node types: {missing}"


def test_all_edge_types_present(built_graph):
    """All 10 edge types exist."""
    present = {e["type"] for e in built_graph["edges"]}
    missing = ALL_EDGE_TYPES - present
    assert not missing, f"Missing edge types: {missing}"


# ---------------------------------------------------------------------------
# Edge counts
# ---------------------------------------------------------------------------

def test_had_visit_edges(built_graph):
    """31 HAD_VISIT edges (patient -> visit)."""
    edges = _edges_of_type(built_graph, "HAD_VISIT")
    assert len(edges) == 31
    for e in edges:
        assert built_graph["nodes"][e["source"]]["type"] == "patient"
        assert built_graph["nodes"][e["target"]]["type"] == "visit"


def test_has_condition_edges(built_graph):
    """6 HAS_CONDITION edges (patient -> condition, discoverable skipped)."""
    edges = _edges_of_type(built_graph, "HAS_CONDITION")
    assert len(edges) == 6
    for e in edges:
        assert built_graph["nodes"][e["source"]]["type"] == "patient"
        assert built_graph["nodes"][e["target"]]["type"] == "condition"


def test_prescribed_edges(built_graph):
    """11 PRESCRIBED edges (patient -> medication)."""
    edges = _edges_of_type(built_graph, "PRESCRIBED")
    assert len(edges) == 11
    for e in edges:
        assert built_graph["nodes"][e["source"]]["type"] == "patient"
        assert built_graph["nodes"][e["target"]]["type"] == "medication"


def test_resulted_in_edges(built_graph):
    """48 RESULTED_IN edges (visit -> lab_result)."""
    edges = _edges_of_type(built_graph, "RESULTED_IN")
    assert len(edges) == 48
    for e in edges:
        assert built_graph["nodes"][e["source"]]["type"] == "visit"
        assert built_graph["nodes"][e["target"]]["type"] == "lab_result"


def test_performed_edges(built_graph):
    """4 PERFORMED edges (visit -> procedure)."""
    edges = _edges_of_type(built_graph, "PERFORMED")
    assert len(edges) == 4
    for e in edges:
        assert built_graph["nodes"][e["source"]]["type"] == "visit"
        assert built_graph["nodes"][e["target"]]["type"] == "procedure"


def test_attended_by_edges(built_graph):
    """31 ATTENDED_BY edges (visit -> provider)."""
    edges = _edges_of_type(built_graph, "ATTENDED_BY")
    assert len(edges) == 31
    for e in edges:
        assert built_graph["nodes"][e["source"]]["type"] == "visit"
        assert built_graph["nodes"][e["target"]]["type"] == "provider"


def test_treated_with_edges(built_graph):
    """10 TREATED_WITH edges (condition -> medication)."""
    edges = _edges_of_type(built_graph, "TREATED_WITH")
    assert len(edges) == 10
    for e in edges:
        assert built_graph["nodes"][e["source"]]["type"] == "condition"
        assert built_graph["nodes"][e["target"]]["type"] == "medication"


def test_monitored_by_edges(built_graph):
    """17 MONITORED_BY edges (medication -> lab_result)."""
    edges = _edges_of_type(built_graph, "MONITORED_BY")
    assert len(edges) == 17
    for e in edges:
        assert built_graph["nodes"][e["source"]]["type"] == "medication"
        assert built_graph["nodes"][e["target"]]["type"] == "lab_result"


def test_referred_to_edges(built_graph):
    """4 REFERRED_TO edges (provider -> provider)."""
    edges = _edges_of_type(built_graph, "REFERRED_TO")
    assert len(edges) == 4
    for e in edges:
        assert built_graph["nodes"][e["source"]]["type"] == "provider"
        assert built_graph["nodes"][e["target"]]["type"] == "provider"


def test_has_family_history_edges(built_graph):
    """3 HAS_FAMILY_HISTORY edges (patient -> family_history)."""
    edges = _edges_of_type(built_graph, "HAS_FAMILY_HISTORY")
    assert len(edges) == 3
    for e in edges:
        assert built_graph["nodes"][e["source"]]["type"] == "patient"
        assert built_graph["nodes"][e["target"]]["type"] == "family_history"


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------

def test_edge_endpoints_valid(built_graph):
    """Every edge source/target exists as a node ID."""
    node_ids = set(built_graph["nodes"].keys())
    for e in built_graph["edges"]:
        assert e["source"] in node_ids, f"Edge source {e['source']} not in nodes"
        assert e["target"] in node_ids, f"Edge target {e['target']} not in nodes"


def test_no_orphan_nodes(built_graph):
    """Every non-patient, non-disease_reference node has at least one edge."""
    targeted = set()
    sourced = set()
    for e in built_graph["edges"]:
        targeted.add(e["target"])
        sourced.add(e["source"])
    connected = targeted | sourced
    # Skip patient nodes (roots) and disease_reference nodes (intentionally standalone)
    for nid, node in built_graph["nodes"].items():
        if node["type"] not in ("patient", "disease_reference"):
            assert nid in connected, f"Orphan node: {nid} ({node['type']})"


def test_loadable_by_graph_module(built_graph, tmp_path):
    """Graph can be loaded by backend/graph.py and queried."""
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(built_graph, indent=2))

    graph = load_graph(str(graph_path))
    assert len(graph.nodes) == built_graph["meta"]["num_nodes"]

    john = get_patient(graph, name="John Smith")
    assert john is not None
    assert john.field_value("name") == "John Smith"

    marcus = get_patient(graph, name="Marcus Reed")
    assert marcus is not None


def test_deterministic(demo_profiles, disease_references):
    """Two calls with same input produce identical output."""
    from scripts.build_graph import build_graph

    result1 = json.dumps(build_graph(demo_profiles, disease_references=disease_references), sort_keys=True)
    result2 = json.dumps(build_graph(demo_profiles, disease_references=disease_references), sort_keys=True)
    assert result1 == result2


def test_phi_tagging_spot_check(built_graph):
    """Spot-check PHI/safe tagging on specific fields."""
    # Find a visit node and check fields
    visits = _nodes_of_type(built_graph, "visit")
    v = visits[0]
    assert v["fields"]["date"]["phi"] is True
    assert v["fields"]["chief_complaint"]["phi"] is False

    # Find a lab and check
    labs = _nodes_of_type(built_graph, "lab_result")
    lab = labs[0]
    assert lab["fields"]["test_name"]["phi"] is False
    assert lab["fields"]["value"]["phi"] is False
    assert lab["fields"]["date"]["phi"] is True

    # Find a medication and check
    meds = _nodes_of_type(built_graph, "medication")
    med = meds[0]
    assert med["fields"]["name"]["phi"] is False
    assert med["fields"]["prescribing_provider"]["phi"] is True


# ---------------------------------------------------------------------------
# Disease reference nodes
# ---------------------------------------------------------------------------

def test_disease_reference_nodes(built_graph):
    """Disease reference nodes exist with correct fields."""
    disease_refs = [n for n in built_graph["nodes"].values() if n["type"] == "disease_reference"]
    assert len(disease_refs) > 0
    for ref in disease_refs:
        fields = ref["fields"]
        assert "name" in fields
        assert "category" in fields
        assert "description" in fields
        assert "symptoms" in fields
        assert "diagnostic_criteria" in fields
        assert "lab_markers" in fields
        assert "epidemiology" in fields
        assert "icd_code" in fields
        # All fields should be safe (not PHI)
        for f in fields.values():
            assert f["phi"] is False


def test_disease_reference_no_edges(built_graph):
    """Disease reference nodes should have no edges."""
    disease_ref_ids = {nid for nid, n in built_graph["nodes"].items() if n["type"] == "disease_reference"}
    for edge in built_graph["edges"]:
        assert edge["source"] not in disease_ref_ids, f"Disease ref {edge['source']} has outgoing edge"
        assert edge["target"] not in disease_ref_ids, f"Disease ref {edge['target']} has incoming edge"


# ---------------------------------------------------------------------------
# Discoverable conditions
# ---------------------------------------------------------------------------

def test_discoverable_conditions_no_has_condition_edge(built_graph):
    """Discoverable conditions have nodes but no HAS_CONDITION edge from patient."""
    condition_nodes = {nid: n for nid, n in built_graph["nodes"].items() if n["type"] == "condition"}
    sle_ids = [nid for nid, n in condition_nodes.items() if "Lupus" in n["fields"]["name"]["value"]]
    solanum_ids = [nid for nid, n in condition_nodes.items() if "Solanum" in n["fields"]["name"]["value"]]

    # These condition nodes should exist
    assert len(sle_ids) > 0, "SLE condition node should exist"
    assert len(solanum_ids) > 0, "Solanum condition node should exist"

    # But no HAS_CONDITION edges should point to them
    has_condition_targets = {e["target"] for e in built_graph["edges"] if e["type"] == "HAS_CONDITION"}
    for sle_id in sle_ids:
        assert sle_id not in has_condition_targets, "SLE should not have HAS_CONDITION edge"
    for sol_id in solanum_ids:
        assert sol_id not in has_condition_targets, "Solanum should not have HAS_CONDITION edge"


def test_discoverable_conditions_still_have_treated_with(built_graph):
    """Medications that treat discoverable conditions still have TREATED_WITH edges."""
    treated_with_edges = [e for e in built_graph["edges"] if e["type"] == "TREATED_WITH"]
    condition_nodes = {nid: n for nid, n in built_graph["nodes"].items() if n["type"] == "condition"}
    sle_ids = {nid for nid, n in condition_nodes.items() if "Lupus" in n["fields"]["name"]["value"]}
    # TREATED_WITH: condition (source) -> medication (target)
    sle_treated = [e for e in treated_with_edges if e["source"] in sle_ids]
    assert len(sle_treated) > 0, "SLE should have TREATED_WITH edges to medications"


def test_condition_nodes_have_sources(built_graph):
    """Condition nodes should have a sources array."""
    conditions = [n for n in built_graph["nodes"].values() if n["type"] == "condition"]
    # At least some conditions should have sources (those with diagnosed_visit)
    with_sources = [c for c in conditions if c.get("sources")]
    assert len(with_sources) > 0, "No condition nodes have sources"
    for cond in with_sources:
        for src in cond["sources"]:
            assert "pdf" in src, f"Source missing 'pdf' key in condition {cond['id']}"
            assert "page" in src, f"Source missing 'page' key in condition {cond['id']}"


def test_medication_nodes_have_sources(built_graph):
    """Medication nodes should have a sources array."""
    medications = [n for n in built_graph["nodes"].values() if n["type"] == "medication"]
    with_sources = [m for m in medications if m.get("sources")]
    assert len(with_sources) > 0, "No medication nodes have sources"
    for med in with_sources:
        for src in med["sources"]:
            assert "pdf" in src, f"Source missing 'pdf' key in medication {med['id']}"
            assert "page" in src, f"Source missing 'page' key in medication {med['id']}"
