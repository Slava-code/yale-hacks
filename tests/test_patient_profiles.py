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
    "id", "name", "age", "sex", "mrn", "dob", "tier", "summary",
    "conditions", "medications", "providers", "visits",
}

# All node types that a demo profile's data should be able to produce
ALL_NODE_TYPES = {
    "patient", "visit", "condition", "medication",
    "lab_result", "procedure", "provider", "family_history",
    "disease_reference",
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

    # disease_reference nodes come from data/disease_references.json, not profiles
    producible_node_types.add("disease_reference")

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


# ---------------------------------------------------------------------------
# All-profile validation (covers generated profiles, not just demo)
# ---------------------------------------------------------------------------

def test_all_profiles_have_required_fields(all_profiles):
    """Every profile must have all required top-level fields."""
    for profile in all_profiles:
        missing = REQUIRED_TOP_LEVEL_FIELDS - set(profile.keys())
        assert not missing, f"{profile['id']} missing: {missing}"


def test_all_profiles_valid_tier(all_profiles):
    """Every profile must have a valid tier."""
    for profile in all_profiles:
        assert profile["tier"] in VALID_TIERS, (
            f"{profile['id']}: invalid tier '{profile['tier']}'"
        )


def test_all_profiles_visit_refs_unique(all_profiles):
    """Visit refs must be unique within each profile."""
    for profile in all_profiles:
        refs = [v["ref"] for v in profile["visits"]]
        dupes = [r for r in refs if refs.count(r) > 1]
        assert not dupes, f"{profile['id']} has duplicate visit refs: {set(dupes)}"


def test_all_profiles_provider_references_resolve(all_profiles):
    """Every provider name used in visits must exist in the providers array."""
    for profile in all_profiles:
        provider_names = {p["name"] for p in profile["providers"]}
        for visit in profile["visits"]:
            assert visit["provider"] in provider_names, (
                f"{profile['id']} visit {visit['ref']}: provider "
                f"'{visit['provider']}' not in providers"
            )


def test_all_profiles_filenames_valid(all_profiles):
    """All document filenames must follow the naming convention."""
    for profile in all_profiles:
        for visit in profile["visits"]:
            doc = visit.get("document")
            if doc:
                assert PDF_FILENAME_PATTERN.match(doc["filename"]), (
                    f"{profile['id']} visit {visit['ref']}: "
                    f"'{doc['filename']}' invalid"
                )
            labs_doc = visit.get("labs_document")
            if labs_doc:
                assert PDF_FILENAME_PATTERN.match(labs_doc["filename"]), (
                    f"{profile['id']} visit {visit['ref']}: "
                    f"labs '{labs_doc['filename']}' invalid"
                )


def test_all_profiles_visits_chronological(all_profiles):
    """Visit dates must be in chronological order in every profile."""
    for profile in all_profiles:
        dates = [v["date"] for v in profile["visits"]]
        assert dates == sorted(dates), (
            f"{profile['id']}: visits not chronological"
        )


def test_all_profiles_conditions_have_icd(all_profiles):
    """Every condition must have a non-empty icd_code."""
    for profile in all_profiles:
        for cond in profile["conditions"]:
            assert cond.get("icd_code"), (
                f"{profile['id']}: condition '{cond['name']}' missing icd_code"
            )


def test_all_profiles_medication_refs_resolve(all_profiles):
    """Medication names in started/discontinued must exist in the medications array."""
    for profile in all_profiles:
        med_names = {m["name"] for m in profile["medications"]}
        for visit in profile["visits"]:
            for med in visit.get("medications_started", []):
                assert med in med_names, (
                    f"{profile['id']} visit {visit['ref']}: "
                    f"'{med}' not in medications"
                )
            for med in visit.get("medications_discontinued", []):
                assert med in med_names, (
                    f"{profile['id']} visit {visit['ref']}: "
                    f"'{med}' not in medications"
                )


def test_all_profiles_valid_visit_types(all_profiles):
    """Every visit must have a valid type."""
    for profile in all_profiles:
        for visit in profile["visits"]:
            assert visit["type"] in VALID_VISIT_TYPES, (
                f"{profile['id']} visit {visit['ref']}: "
                f"invalid type '{visit['type']}'"
            )


def test_all_profiles_valid_condition_statuses(all_profiles):
    """Every condition must have a valid status."""
    for profile in all_profiles:
        for cond in profile["conditions"]:
            assert cond["status"] in VALID_CONDITION_STATUSES, (
                f"{profile['id']}: condition '{cond['name']}' "
                f"invalid status '{cond['status']}'"
            )


def test_all_profiles_valid_medication_statuses(all_profiles):
    """Every medication must have a valid status."""
    for profile in all_profiles:
        for med in profile["medications"]:
            assert med["status"] in VALID_MEDICATION_STATUSES, (
                f"{profile['id']}: medication '{med['name']}' "
                f"invalid status '{med['status']}'"
            )


def test_all_profiles_valid_lab_flags(all_profiles):
    """Every lab result must have a valid flag."""
    for profile in all_profiles:
        for visit in profile["visits"]:
            for lab in visit.get("labs", []):
                assert lab["flag"] in VALID_LAB_FLAGS, (
                    f"{profile['id']} visit {visit['ref']}: "
                    f"lab '{lab['test']}' invalid flag '{lab['flag']}'"
                )


def test_all_profiles_tier_visit_counts(all_profiles):
    """Each tier must have the required number of visits."""
    for profile in all_profiles:
        nv = len(profile["visits"])
        tier = profile["tier"]
        if tier in ("demo", "complex"):
            assert nv >= 15, (
                f"{profile['id']}: {tier} tier requires >= 15 visits, got {nv}"
            )
        elif tier == "moderate":
            assert 5 <= nv <= 10, (
                f"{profile['id']}: moderate tier requires 5-10 visits, got {nv}"
            )
        elif tier == "simple":
            assert 2 <= nv <= 3, (
                f"{profile['id']}: simple tier requires 2-3 visits, got {nv}"
            )


def test_all_profiles_complex_demo_have_storyline(all_profiles):
    """Demo and complex tier profiles must have a non-empty storyline."""
    for profile in all_profiles:
        if profile["tier"] in ("demo", "complex"):
            assert profile.get("storyline"), (
                f"{profile['id']}: {profile['tier']} tier requires a storyline"
            )


def test_patient_distribution(all_profiles):
    """The dataset must have a minimum number of each tier."""
    tiers = [p["tier"] for p in all_profiles]
    assert tiers.count("demo") >= 2, f"Need >= 2 demo, got {tiers.count('demo')}"
    assert tiers.count("complex") >= 5, f"Need >= 5 complex, got {tiers.count('complex')}"
    assert tiers.count("moderate") >= 10, f"Need >= 10 moderate, got {tiers.count('moderate')}"
    assert tiers.count("simple") >= 15, f"Need >= 15 simple, got {tiers.count('simple')}"


# ---------------------------------------------------------------------------
# DOB and discoverable conditions
# ---------------------------------------------------------------------------

def test_profile_has_valid_dob(all_profiles):
    """Every profile must have a valid ISO date dob."""
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for profile in all_profiles:
        assert "dob" in profile, f"{profile['id']} missing dob"
        assert date_pattern.match(profile["dob"]), f"{profile['id']} invalid dob: {profile['dob']}"


def test_demo_patients_have_discoverable_conditions(demo_profiles):
    """Demo patients should have at least one discoverable condition."""
    for profile in demo_profiles:
        discoverable = [c for c in profile["conditions"] if c.get("discoverable", False)]
        assert len(discoverable) > 0, f"{profile['id']} has no discoverable conditions"
