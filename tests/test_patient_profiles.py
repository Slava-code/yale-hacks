"""Tests for patient profile JSON validation.

These tests validate that demo patient profiles follow the schema
defined in data/patients/SCHEMA.md and are internally consistent.
"""

import json
import re
from pathlib import Path

import pytest

from tests.conftest import DEMO_PROFILE_IDS, PATIENTS_DIR

# Valid values for enum fields
VALID_TIERS = {"demo", "complex", "moderate", "simple"}
VALID_VISIT_TYPES = {"initial", "follow-up", "emergency", "routine", "consult"}
VALID_CONDITION_STATUSES = {"active", "resolved", "chronic"}
VALID_MEDICATION_STATUSES = {"active", "discontinued"}
VALID_LAB_FLAGS = {"normal", "high", "low", "critical"}
VALID_DOC_TYPES = {
    "intake_form",
    "progress_note",
    "lab_report",
    "imaging_report",
    "discharge_summary",
    "referral_letter",
    "consult_note",
    "cdc_advisory",
}

REQUIRED_TOP_LEVEL_FIELDS = {
    "id", "name", "age", "sex", "mrn", "tier", "summary",
    "conditions", "medications", "providers", "visits",
}

# All node types that a demo profile's data should be able to produce
ALL_NODE_TYPES = {
    "patient", "visit", "condition", "medication",
    "lab_result", "procedure", "provider", "family_history",
}

# All edge types that a demo profile's data should be able to produce
ALL_EDGE_TYPES = {
    "HAD_VISIT", "HAS_CONDITION", "PRESCRIBED", "RESULTED_IN",
    "PERFORMED", "ATTENDED_BY", "TREATED_WITH", "MONITORED_BY",
    "REFERRED_TO", "HAS_FAMILY_HISTORY",
}

# PDF naming: {type}_{lastname}_{yyyy}_{mon}.pdf with optional _N suffix
PDF_FILENAME_PATTERN = re.compile(
    r"^[a-z_]+_[a-z]+_\d{4}_[a-z]{3}(_\d+)?\.pdf$"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_profile(patient_id: str) -> dict:
    path = PATIENTS_DIR / f"{patient_id}.json"
    with open(path) as f:
        return json.load(f)


def _all_demo_profiles():
    return [_load_profile(pid) for pid in DEMO_PROFILE_IDS]


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("patient_id", DEMO_PROFILE_IDS)
def test_profile_files_exist(patient_id):
    """Demo profile JSON files must exist."""
    path = PATIENTS_DIR / f"{patient_id}.json"
    assert path.exists(), f"{path} does not exist"


# ---------------------------------------------------------------------------
# Top-level structure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("patient_id", DEMO_PROFILE_IDS)
def test_profile_required_fields(patient_id):
    """Each profile has all required top-level fields."""
    profile = _load_profile(patient_id)
    missing = REQUIRED_TOP_LEVEL_FIELDS - set(profile.keys())
    assert not missing, f"{patient_id} missing fields: {missing}"


@pytest.mark.parametrize("patient_id", DEMO_PROFILE_IDS)
def test_profile_demo_tier_has_storyline(patient_id):
    """Demo-tier profiles must have a non-empty storyline."""
    profile = _load_profile(patient_id)
    if profile["tier"] == "demo":
        assert profile.get("storyline"), f"{patient_id}: demo tier requires a storyline"


@pytest.mark.parametrize("patient_id", DEMO_PROFILE_IDS)
def test_profile_demo_tier_min_visits(patient_id):
    """Demo-tier profiles must have at least 15 visits."""
    profile = _load_profile(patient_id)
    if profile["tier"] == "demo":
        assert len(profile["visits"]) >= 15, (
            f"{patient_id}: demo tier requires >= 15 visits, got {len(profile['visits'])}"
        )


# ---------------------------------------------------------------------------
# Internal consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("patient_id", DEMO_PROFILE_IDS)
def test_profile_visit_refs_unique(patient_id):
    """No duplicate visit refs within a profile."""
    profile = _load_profile(patient_id)
    refs = [v["ref"] for v in profile["visits"]]
    dupes = [r for r in refs if refs.count(r) > 1]
    assert not dupes, f"{patient_id} has duplicate visit refs: {set(dupes)}"


@pytest.mark.parametrize("patient_id", DEMO_PROFILE_IDS)
def test_profile_provider_references_resolve(patient_id):
    """Every provider name in visits must exist in the providers array."""
    profile = _load_profile(patient_id)
    provider_names = {p["name"] for p in profile["providers"]}
    for visit in profile["visits"]:
        assert visit["provider"] in provider_names, (
            f"{patient_id} visit {visit['ref']}: provider '{visit['provider']}' "
            f"not in providers array"
        )


@pytest.mark.parametrize("patient_id", DEMO_PROFILE_IDS)
def test_profile_medication_references_resolve(patient_id):
    """Every medication in started/discontinued must exist in the medications array."""
    profile = _load_profile(patient_id)
    med_names = {m["name"] for m in profile["medications"]}
    for visit in profile["visits"]:
        for med in visit.get("medications_started", []):
            assert med in med_names, (
                f"{patient_id} visit {visit['ref']}: medication_started '{med}' "
                f"not in medications array"
            )
        for med in visit.get("medications_discontinued", []):
            assert med in med_names, (
                f"{patient_id} visit {visit['ref']}: medication_discontinued '{med}' "
                f"not in medications array"
            )


@pytest.mark.parametrize("patient_id", DEMO_PROFILE_IDS)
def test_profile_document_filenames_follow_convention(patient_id):
    """All document filenames must match the naming convention."""
    profile = _load_profile(patient_id)
    for visit in profile["visits"]:
        doc = visit.get("document")
        if doc:
            fname = doc["filename"]
            assert PDF_FILENAME_PATTERN.match(fname), (
                f"{patient_id} visit {visit['ref']}: filename '{fname}' "
                f"doesn't match convention"
            )
        labs_doc = visit.get("labs_document")
        if labs_doc:
            fname = labs_doc["filename"]
            assert PDF_FILENAME_PATTERN.match(fname), (
                f"{patient_id} visit {visit['ref']}: labs filename '{fname}' "
                f"doesn't match convention"
            )


@pytest.mark.parametrize("patient_id", DEMO_PROFILE_IDS)
def test_profile_visits_chronological(patient_id):
    """Visit dates must be in chronological order."""
    profile = _load_profile(patient_id)
    dates = [v["date"] for v in profile["visits"]]
    assert dates == sorted(dates), (
        f"{patient_id}: visits are not in chronological order"
    )


@pytest.mark.parametrize("patient_id", DEMO_PROFILE_IDS)
def test_profile_conditions_have_icd_codes(patient_id):
    """All conditions must have a non-empty icd_code."""
    profile = _load_profile(patient_id)
    for cond in profile["conditions"]:
        assert cond.get("icd_code"), (
            f"{patient_id}: condition '{cond['name']}' missing icd_code"
        )


# ---------------------------------------------------------------------------
# Cross-profile uniqueness
# ---------------------------------------------------------------------------

def test_profile_no_duplicate_mrns(all_profiles):
    """No two profiles should share an MRN."""
    mrns = [p["mrn"] for p in all_profiles]
    dupes = [m for m in mrns if mrns.count(m) > 1]
    assert not dupes, f"Duplicate MRNs: {set(dupes)}"


def test_profile_no_duplicate_names(all_profiles):
    """No two profiles should share a name."""
    names = [p["name"] for p in all_profiles]
    dupes = [n for n in names if names.count(n) > 1]
    assert not dupes, f"Duplicate names: {set(dupes)}"


# ---------------------------------------------------------------------------
# Family history
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("patient_id", DEMO_PROFILE_IDS)
def test_profile_family_history_structure(patient_id):
    """Family history entries must have relation and condition."""
    profile = _load_profile(patient_id)
    for entry in profile.get("family_history", []):
        assert "relation" in entry, f"{patient_id}: family_history entry missing 'relation'"
        assert "condition" in entry, f"{patient_id}: family_history entry missing 'condition'"


# ---------------------------------------------------------------------------
# Graph function coverage
# ---------------------------------------------------------------------------

def test_profile_exercises_all_graph_functions(demo_profiles):
    """Demo profiles collectively should produce data for all node/edge types.

    This checks that the profile data is rich enough to exercise all 12
    graph query functions when converted to a graph.
    """
    producible_node_types = set()
    producible_edge_types = set()

    for profile in demo_profiles:
        producible_node_types.add("patient")

        if profile.get("visits"):
            producible_node_types.add("visit")
            producible_edge_types.add("HAD_VISIT")

        if profile.get("conditions"):
            producible_node_types.add("condition")
            producible_edge_types.add("HAS_CONDITION")

        if profile.get("medications"):
            producible_node_types.add("medication")
            producible_edge_types.add("PRESCRIBED")

        if profile.get("providers"):
            producible_node_types.add("provider")

        if profile.get("family_history"):
            producible_node_types.add("family_history")
            producible_edge_types.add("HAS_FAMILY_HISTORY")

        for visit in profile.get("visits", []):
            if visit.get("labs"):
                producible_node_types.add("lab_result")
                producible_edge_types.add("RESULTED_IN")
            if visit.get("procedures"):
                producible_node_types.add("procedure")
                producible_edge_types.add("PERFORMED")
            if visit.get("provider"):
                producible_edge_types.add("ATTENDED_BY")
            if visit.get("referrals"):
                producible_edge_types.add("REFERRED_TO")

        for med in profile.get("medications", []):
            if med.get("treats"):
                producible_edge_types.add("TREATED_WITH")
            if med.get("monitored_by_labs"):
                producible_edge_types.add("MONITORED_BY")

    missing_nodes = ALL_NODE_TYPES - producible_node_types
    assert not missing_nodes, f"Profiles can't produce node types: {missing_nodes}"

    missing_edges = ALL_EDGE_TYPES - producible_edge_types
    assert not missing_edges, f"Profiles can't produce edge types: {missing_edges}"
