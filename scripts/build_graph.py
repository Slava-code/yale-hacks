"""
Deterministic graph builder — transforms patient profile JSONs into graph.json.

No AI/API calls needed. The patient profiles already contain all structured data;
this script mechanically converts them into the graph format expected by
backend/graph.py and docs/interfaces.md §4.

Usage:
    python scripts/build_graph.py [--output data/graph.json] [--patients-dir data/patients]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Field wrapper helpers
# ---------------------------------------------------------------------------

def _phi(value):
    return {"value": value, "phi": True}


def _safe(value):
    return {"value": value, "phi": False}


# ---------------------------------------------------------------------------
# Label formatting
# ---------------------------------------------------------------------------

_VISIT_TYPE_LABELS = {
    "initial": "Initial Visit",
    "follow-up": "Follow-up",
    "emergency": "Emergency",
    "routine": "Routine",
    "consult": "Consult",
}

_MONTH_ABBR = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _visit_label(visit_type: str, date_str: str) -> str:
    """Format: 'Follow-up — Oct 2025'."""
    label = _VISIT_TYPE_LABELS.get(visit_type, visit_type.title())
    year, month, _ = date_str.split("-")
    mon = _MONTH_ABBR[int(month)]
    return f"{label} — {mon} {year}"


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------

class _IdGen:
    """Globally sequential ID generator per node type."""

    def __init__(self):
        self._counters: dict[str, int] = {}

    def next(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}_{self._counters[prefix]:03d}"


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def build_graph(profiles: list[dict]) -> dict:
    """Pure function: list of patient profile dicts → graph dict."""
    ids = _IdGen()
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    # Shared across patients for deduplication
    provider_name_to_id: dict[str, str] = {}

    # Sort profiles by ID for determinism
    sorted_profiles = sorted(profiles, key=lambda p: p["id"])

    for profile in sorted_profiles:
        _process_patient(profile, ids, nodes, edges, provider_name_to_id)

    meta = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "num_patients": len([n for n in nodes.values() if n["type"] == "patient"]),
        "num_nodes": len(nodes),
        "num_edges": len(edges),
    }

    return {"meta": meta, "nodes": nodes, "edges": edges}


def _process_patient(
    profile: dict,
    ids: _IdGen,
    nodes: dict,
    edges: list,
    provider_name_to_id: dict,
):
    patient_id = profile["id"]

    # --- Visit ref → visit data lookup ---
    visit_lookup = {v["ref"]: v for v in profile["visits"]}

    # --- Provider nodes (deduplicated by name) ---
    for prov in profile.get("providers", []):
        if prov["name"] not in provider_name_to_id:
            prov_id = ids.next("provider")
            provider_name_to_id[prov["name"]] = prov_id
            nodes[prov_id] = {
                "id": prov_id,
                "type": "provider",
                "label": prov["name"],
                "fields": {
                    "name": _phi(prov["name"]),
                    "role": _safe(prov["role"]),
                    "department": _safe(prov["department"]),
                },
            }

    # --- Patient node ---
    first_doc = profile["visits"][0]["document"]["filename"] if profile["visits"] else None
    nodes[patient_id] = {
        "id": patient_id,
        "type": "patient",
        "label": profile["name"],
        "fields": {
            "name": _phi(profile["name"]),
            "age": _safe(profile["age"]),
            "sex": _safe(profile["sex"]),
            "mrn": _phi(profile["mrn"]),
            "summary": _safe(profile["summary"]),
        },
        "source_pdf": first_doc,
        "source_page": 1,
    }

    # --- Condition nodes ---
    condition_name_to_id: dict[str, str] = {}
    for cond in profile.get("conditions", []):
        cond_id = ids.next("condition")
        condition_name_to_id[cond["name"]] = cond_id
        nodes[cond_id] = {
            "id": cond_id,
            "type": "condition",
            "label": cond["name"],
            "fields": {
                "name": _safe(cond["name"]),
                "icd_code": _safe(cond.get("icd_code", "")),
                "status": _safe(cond["status"]),
            },
        }
        edges.append({"source": patient_id, "target": cond_id, "type": "HAS_CONDITION"})

    # --- Medication nodes ---
    medication_name_to_id: dict[str, str] = {}
    for med in profile.get("medications", []):
        med_id = ids.next("medication")
        medication_name_to_id[med["name"]] = med_id

        # Resolve prescribing provider and start date from start_visit
        start_visit = visit_lookup.get(med.get("start_visit", ""), {})
        prescribing_provider = start_visit.get("provider", "")
        start_date = start_visit.get("date", "")

        nodes[med_id] = {
            "id": med_id,
            "type": "medication",
            "label": f"{med['name']} {med['dosage']}",
            "fields": {
                "name": _safe(med["name"]),
                "dosage": _safe(med["dosage"]),
                "frequency": _safe(med["frequency"]),
                "prescribing_provider": _phi(prescribing_provider),
                "start_date": _phi(start_date),
                "status": _safe(med["status"]),
            },
        }
        edges.append({"source": patient_id, "target": med_id, "type": "PRESCRIBED"})

        # TREATED_WITH: condition → medication
        treats = med.get("treats")
        if treats and treats in condition_name_to_id:
            edges.append({
                "source": condition_name_to_id[treats],
                "target": med_id,
                "type": "TREATED_WITH",
            })

    # --- Visit nodes, lab nodes, procedure nodes ---
    # Track all lab nodes for MONITORED_BY resolution
    lab_test_name_to_ids: dict[str, list[str]] = {}

    for visit in profile["visits"]:
        visit_id = ids.next("visit")

        nodes[visit_id] = {
            "id": visit_id,
            "type": "visit",
            "label": _visit_label(visit["type"], visit["date"]),
            "fields": {
                "date": _phi(visit["date"]),
                "visit_type": _safe(visit["type"]),
                "chief_complaint": _safe(visit["chief_complaint"]),
                "attending_provider": _phi(visit["provider"]),
                "notes": _safe(visit["narrative"]),
            },
            "source_pdf": visit["document"]["filename"],
            "source_page": 1,
        }
        edges.append({"source": patient_id, "target": visit_id, "type": "HAD_VISIT"})

        # ATTENDED_BY: visit → provider
        prov_id = provider_name_to_id.get(visit["provider"])
        if prov_id:
            edges.append({"source": visit_id, "target": prov_id, "type": "ATTENDED_BY"})

        # Lab result nodes
        for i, lab in enumerate(visit.get("labs", []), start=1):
            lab_id = ids.next("lab_result")
            labs_doc = visit.get("labs_document")
            source_pdf = labs_doc["filename"] if labs_doc else visit["document"]["filename"]

            nodes[lab_id] = {
                "id": lab_id,
                "type": "lab_result",
                "label": lab["test"],
                "fields": {
                    "test_name": _safe(lab["test"]),
                    "value": _safe(lab["value"]),
                    "unit": _safe(lab["unit"]),
                    "reference_range": _safe(lab["range"]),
                    "flag": _safe(lab["flag"]),
                    "date": _phi(visit["date"]),
                },
                "source_pdf": source_pdf,
                "source_page": i,
            }
            edges.append({"source": visit_id, "target": lab_id, "type": "RESULTED_IN"})

            # Track for MONITORED_BY
            lab_test_name_to_ids.setdefault(lab["test"], []).append(lab_id)

        # Procedure nodes
        for proc in visit.get("procedures", []):
            proc_id = ids.next("procedure")
            nodes[proc_id] = {
                "id": proc_id,
                "type": "procedure",
                "label": proc["name"],
                "fields": {
                    "name": _safe(proc["name"]),
                    "date": _phi(visit["date"]),
                    "provider": _phi(visit["provider"]),
                    "outcome": _safe(proc["outcome"]),
                },
                "source_pdf": visit["document"]["filename"],
                "source_page": 1,
            }
            edges.append({"source": visit_id, "target": proc_id, "type": "PERFORMED"})

        # REFERRED_TO: visit provider → referral target provider
        for ref in visit.get("referrals", []):
            from_prov_id = provider_name_to_id.get(visit["provider"])
            to_prov_id = provider_name_to_id.get(ref["to"])
            if from_prov_id and to_prov_id:
                edges.append({
                    "source": from_prov_id,
                    "target": to_prov_id,
                    "type": "REFERRED_TO",
                })

    # --- Family history nodes ---
    for fh in profile.get("family_history", []):
        fh_id = ids.next("family_hx")
        first_visit_doc = profile["visits"][0]["document"]["filename"] if profile["visits"] else None
        nodes[fh_id] = {
            "id": fh_id,
            "type": "family_history",
            "label": f"{fh['relation'].title()} — {fh['condition']}",
            "fields": {
                "relation": _safe(fh["relation"]),
                "condition": _safe(fh["condition"]),
                "diagnosed_age": _safe(fh.get("diagnosed_age")),
            },
            "source_pdf": first_visit_doc,
            "source_page": 1,
        }
        edges.append({"source": patient_id, "target": fh_id, "type": "HAS_FAMILY_HISTORY"})

    # --- MONITORED_BY edges ---
    for med in profile.get("medications", []):
        med_id = medication_name_to_id.get(med["name"])
        if not med_id:
            continue
        for lab_name in med.get("monitored_by_labs", []):
            for lab_id in lab_test_name_to_ids.get(lab_name, []):
                edges.append({
                    "source": med_id,
                    "target": lab_id,
                    "type": "MONITORED_BY",
                })


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build graph.json from patient profiles")
    parser.add_argument(
        "--patients-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "patients",
        help="Directory containing patient_*.json files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "graph.json",
        help="Output path for graph.json",
    )
    args = parser.parse_args()

    # Load all patient profiles
    profiles = []
    for path in sorted(args.patients_dir.glob("patient_*.json")):
        with open(path) as f:
            profiles.append(json.load(f))

    if not profiles:
        print(f"No patient profiles found in {args.patients_dir}")
        return

    graph = build_graph(profiles)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(graph, f, indent=2)

    print(f"Built graph: {graph['meta']['num_patients']} patients, "
          f"{graph['meta']['num_nodes']} nodes, {graph['meta']['num_edges']} edges")
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
