"""
Knowledge graph query module.

Public API for the gatekeeper and backend to query the in-memory knowledge graph.
Supports 9 node types including disease_reference (standalone institutional knowledge).
Spec: docs/interfaces.md §3-4.

Person 3 implements this module; Person 2 calls it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data types — one per node kind, plus Graph and TraversalPath
# ---------------------------------------------------------------------------

@dataclass
class Node:
    id: str
    type: str
    label: str
    fields: dict  # {field_name: {"value": ..., "phi": bool}}
    source_pdf: str | None = None
    source_page: int | None = None

    def field_value(self, name: str):
        """Convenience: get the unwrapped value of a field, or None."""
        f = self.fields.get(name)
        return f["value"] if f else None


# Thin aliases so the function signatures match the spec.
# Same structure — the `type` field distinguishes them at runtime.
Patient = Node
Visit = Node
LabResult = Node
Medication = Node
Condition = Node
Procedure = Node
Provider = Node
DiseaseReference = Node


@dataclass
class TraversalPath:
    nodes: list[Node]
    edges: list[dict]  # [{"source": str, "target": str, "type": str}]


@dataclass
class Graph:
    meta: dict
    nodes: dict[str, Node]  # id -> Node
    edges: list[dict]
    # Pre-built indexes (source_id -> list[edge], target_id -> list[edge])
    _edges_from: dict[str, list[dict]] = field(default_factory=dict, repr=False)
    _edges_to: dict[str, list[dict]] = field(default_factory=dict, repr=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_node(node_id: str, raw: dict) -> Node:
    return Node(
        id=node_id,
        type=raw["type"],
        label=raw["label"],
        fields=raw.get("fields", {}),
        source_pdf=raw.get("source_pdf"),
        source_page=raw.get("source_page"),
    )


def _build_indexes(graph: Graph) -> None:
    for edge in graph.edges:
        graph._edges_from.setdefault(edge["source"], []).append(edge)
        graph._edges_to.setdefault(edge["target"], []).append(edge)


def _targets(graph: Graph, source_id: str, edge_type: str) -> list[Node]:
    """Return all target nodes reachable from source_id via edges of edge_type."""
    return [
        graph.nodes[e["target"]]
        for e in graph._edges_from.get(source_id, [])
        if e["type"] == edge_type and e["target"] in graph.nodes
    ]


def _sources(graph: Graph, target_id: str, edge_type: str) -> list[Node]:
    """Return all source nodes that point to target_id via edges of edge_type."""
    return [
        graph.nodes[e["source"]]
        for e in graph._edges_to.get(target_id, [])
        if e["type"] == edge_type and e["source"] in graph.nodes
    ]


def _sort_by_date(nodes: list[Node], date_field: str = "date", desc: bool = True) -> list[Node]:
    """Sort nodes by a date field. Nodes missing the field go to the end."""
    def key(n: Node):
        v = n.field_value(date_field)
        return v if v else ""
    return sorted(nodes, key=key, reverse=desc)


# ---------------------------------------------------------------------------
# Public API — matches docs/interfaces.md §3
# ---------------------------------------------------------------------------

def load_graph(path: str) -> Graph:
    """Load graph.json into memory. Called once at startup."""
    raw = json.loads(Path(path).read_text())
    nodes = {nid: _build_node(nid, ndata) for nid, ndata in raw["nodes"].items()}
    graph = Graph(
        meta=raw.get("meta", {}),
        nodes=nodes,
        edges=raw.get("edges", []),
    )
    _build_indexes(graph)
    return graph


def get_patient(graph: Graph, *, name: str | None = None, id: str | None = None) -> Patient | None:
    """Find a patient by real name or internal ID."""
    if id and id in graph.nodes:
        node = graph.nodes[id]
        return node if node.type == "patient" else None
    if name:
        name_lower = name.lower()
        # Try exact match first
        for node in graph.nodes.values():
            if node.type == "patient" and node.field_value("name") and node.field_value("name").lower() == name_lower:
                return node
        # Fall back to substring match (e.g., "Valentine" matches "Valentine Torres")
        candidates = []
        for node in graph.nodes.values():
            if node.type == "patient" and node.field_value("name"):
                patient_name = node.field_value("name").lower()
                if name_lower in patient_name or patient_name in name_lower:
                    candidates.append(node)
        if len(candidates) == 1:
            return candidates[0]
    return None


def get_patient_visits(graph: Graph, patient_id: str) -> list[Visit]:
    """All visits for a patient, sorted by date descending."""
    return _sort_by_date(_targets(graph, patient_id, "HAD_VISIT"))


def get_visit_labs(graph: Graph, visit_id: str) -> list[LabResult]:
    """Lab results from a specific visit."""
    return _targets(graph, visit_id, "RESULTED_IN")


def get_patient_labs(graph: Graph, patient_id: str) -> list[LabResult]:
    """All lab results across all visits for a patient, sorted by date descending."""
    labs = []
    for visit in get_patient_visits(graph, patient_id):
        labs.extend(get_visit_labs(graph, visit.id))
    return _sort_by_date(labs)


def get_patient_medications(graph: Graph, patient_id: str) -> list[Medication]:
    """All medications for a patient (active and discontinued)."""
    return _targets(graph, patient_id, "PRESCRIBED")


def get_patient_conditions(graph: Graph, patient_id: str) -> list[Condition]:
    """All conditions for a patient."""
    return _targets(graph, patient_id, "HAS_CONDITION")


def get_patient_procedures(graph: Graph, patient_id: str) -> list[Procedure]:
    """All procedures for a patient (via visits)."""
    procs = []
    for visit in get_patient_visits(graph, patient_id):
        procs.extend(_targets(graph, visit.id, "PERFORMED"))
    return _sort_by_date(procs)


def get_patient_providers(graph: Graph, patient_id: str) -> list[Provider]:
    """All providers who have attended this patient."""
    seen = set()
    providers = []
    for visit in get_patient_visits(graph, patient_id):
        for prov in _targets(graph, visit.id, "ATTENDED_BY"):
            if prov.id not in seen:
                seen.add(prov.id)
                providers.append(prov)
    return providers


def get_family_history(graph: Graph, patient_id: str) -> list[dict]:
    """Family medical history entries for a patient.
    Returns: [{"relation": "mother", "condition": "SLE", "diagnosed_age": 35, "source_pdf": "...", "source_page": N}]

    Family history nodes are type "family_history" connected via HAS_FAMILY_HISTORY edges.
    If no such nodes exist, returns an empty list.
    """
    results = []
    for node in _targets(graph, patient_id, "HAS_FAMILY_HISTORY"):
        results.append({
            "relation": node.field_value("relation"),
            "condition": node.field_value("condition"),
            "diagnosed_age": node.field_value("diagnosed_age"),
            "source_pdf": node.source_pdf,
            "source_page": node.source_page,
        })
    return results


def get_node_by_id(graph: Graph, node_id: str) -> Node | None:
    """Generic node lookup by ID."""
    return graph.nodes.get(node_id)


def search_nodes(graph: Graph, query: str, node_type: str | None = None) -> list[Node]:
    """Simple text search across node labels and metadata.
    Used when the gatekeeper needs to find relevant nodes for a free-form question.
    """
    query_lower = query.lower()
    results = []
    for node in graph.nodes.values():
        if node_type and node.type != node_type:
            continue
        # Search label
        if query_lower in node.label.lower():
            results.append(node)
            continue
        # Search field values
        for f in node.fields.values():
            val = str(f.get("value", ""))
            if query_lower in val.lower():
                results.append(node)
                break
    return results


def search_disease_references(graph: Graph, query: str) -> list[DiseaseReference]:
    """Search disease reference nodes by symptom keywords.

    Convenience wrapper around search_nodes() restricted to the
    disease_reference node type. Used by the gatekeeper to find
    candidate diagnoses that match observed clinical evidence.
    """
    return search_nodes(graph, query, node_type="disease_reference")


def get_traversal_path(graph: Graph, node_ids: list[str]) -> TraversalPath:
    """Given a list of accessed node IDs, return the nodes and connecting edges.
    Used to emit graph_traversal events to the frontend.
    """
    id_set = set(node_ids)
    nodes = [graph.nodes[nid] for nid in node_ids if nid in graph.nodes]
    edges = [e for e in graph.edges if e["source"] in id_set and e["target"] in id_set]
    return TraversalPath(nodes=nodes, edges=edges)
