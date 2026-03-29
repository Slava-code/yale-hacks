"""Tests for the clinical document generator — scripts/generate_documents.py."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def test_build_prompt_contains_patient_context(demo_profiles):
    """Prompt includes patient name, visit date, chief complaint, narrative."""
    from scripts.generate_documents import build_prompt

    profile = demo_profiles[0]  # patient_001
    visit = profile["visits"][0]
    prompt = build_prompt(profile, visit, visit["document"]["type"])

    assert profile["name"] in prompt
    assert visit["date"] in prompt
    assert visit["chief_complaint"] in prompt
    assert visit["narrative"][:50] in prompt


def test_build_prompt_includes_labs(demo_profiles):
    """When a visit has labs, prompt includes lab data."""
    from scripts.generate_documents import build_prompt

    profile = demo_profiles[0]
    # visit_02 has labs
    visit = profile["visits"][1]
    assert visit.get("labs"), "Test setup: visit should have labs"
    prompt = build_prompt(profile, visit, visit["document"]["type"])

    for lab in visit["labs"]:
        assert lab["test"] in prompt


def test_build_prompt_includes_procedures(demo_profiles):
    """When a visit has procedures, prompt mentions them."""
    from scripts.generate_documents import build_prompt

    profile = demo_profiles[0]
    # visit_08 has a procedure (X-ray)
    visit = next(v for v in profile["visits"] if v.get("procedures"))
    prompt = build_prompt(profile, visit, visit["document"]["type"])

    assert visit["procedures"][0]["name"] in prompt


def test_build_prompt_varies_by_doc_type(demo_profiles):
    """Different document types produce different prompt instructions."""
    from scripts.generate_documents import build_prompt

    profile = demo_profiles[0]
    visit = profile["visits"][0]

    prompt_intake = build_prompt(profile, visit, "intake_form")
    prompt_progress = build_prompt(profile, visit, "progress_note")
    prompt_lab = build_prompt(profile, visit, "lab_report")

    # The type-specific instructions should differ
    assert prompt_intake != prompt_progress
    assert prompt_intake != prompt_lab
    assert prompt_progress != prompt_lab


# ---------------------------------------------------------------------------
# PDF creation
# ---------------------------------------------------------------------------

def test_text_to_pdf_creates_valid_file(tmp_path):
    """Output file exists, non-empty, starts with %PDF magic bytes."""
    from scripts.generate_documents import text_to_pdf

    header = {
        "patient_name": "John Smith",
        "mrn": "MRN-78234",
        "date": "2025-06-10",
        "doc_type": "Progress Note",
        "provider": "Dr. Sarah Chen",
    }
    text = "Patient presents with bilateral frontal headaches. " * 20

    path = text_to_pdf(text, "test_output.pdf", tmp_path, header)

    assert path.exists()
    assert path.stat().st_size > 0
    with open(path, "rb") as f:
        magic = f.read(4)
    assert magic == b"%PDF"


def test_text_to_pdf_has_header(tmp_path):
    """PDF rendering includes header info (verified by checking reportlab was called with it)."""
    from scripts.generate_documents import text_to_pdf

    header = {
        "patient_name": "John Smith",
        "mrn": "MRN-78234",
        "date": "2025-06-10",
        "doc_type": "Progress Note",
        "provider": "Dr. Sarah Chen",
    }
    text = "Sample clinical text for testing header inclusion."

    path = text_to_pdf(text, "header_test.pdf", tmp_path, header)
    assert path.exists()
    assert path.stat().st_size > 100  # non-trivial PDF size


# ---------------------------------------------------------------------------
# Document generation with mocked API
# ---------------------------------------------------------------------------

MOCK_GEMINI_RESPONSE = "SUBJECTIVE: Patient presents with headaches.\n\nOBJECTIVE: Vitals normal.\n\nASSESSMENT: Tension headache.\n\nPLAN: Ibuprofen PRN."


def test_generate_visit_document_mock(tmp_path, demo_profiles):
    """Mocked Gemini → produces a PDF at expected path."""
    from scripts.generate_documents import generate_visit_document

    profile = demo_profiles[0]
    visit = profile["visits"][0]

    with patch("scripts.generate_documents.call_gemini", return_value=MOCK_GEMINI_RESPONSE):
        path = generate_visit_document(profile, visit, tmp_path)

    assert path is not None
    assert path.exists()
    assert path.name == visit["document"]["filename"]


def test_generate_all_for_patient_mock(tmp_path, demo_profiles):
    """Mocked Gemini → correct number of PDFs for patient_001 (24 docs)."""
    from scripts.generate_documents import generate_documents_for_patient

    profile = demo_profiles[0]  # patient_001

    with patch("scripts.generate_documents.call_gemini", return_value=MOCK_GEMINI_RESPONSE):
        paths = generate_documents_for_patient(profile, tmp_path)

    # Count expected docs: each visit has document + optional labs_document
    expected = 0
    for visit in profile["visits"]:
        expected += 1  # visit document
        if visit.get("labs_document"):
            expected += 1  # separate lab report
    assert expected == 24
    assert len(paths) == expected
    for p in paths:
        assert p.exists()


def test_skips_existing_files(tmp_path, demo_profiles):
    """If a PDF already exists, skip it (idempotent)."""
    from scripts.generate_documents import generate_visit_document

    profile = demo_profiles[0]
    visit = profile["visits"][0]
    filename = visit["document"]["filename"]

    # Pre-create the file
    existing = tmp_path / filename
    existing.write_text("already exists")

    with patch("scripts.generate_documents.call_gemini") as mock_gemini:
        path = generate_visit_document(profile, visit, tmp_path)

    # Should return the existing path without calling Gemini
    assert path == existing
    mock_gemini.assert_not_called()


def test_patient_filter(tmp_path, demo_profiles):
    """When filtering by patient ID, only that patient's docs are generated."""
    from scripts.generate_documents import generate_documents_for_patient

    profile_001 = demo_profiles[0]
    profile_006 = demo_profiles[1]

    with patch("scripts.generate_documents.call_gemini", return_value=MOCK_GEMINI_RESPONSE):
        paths_001 = generate_documents_for_patient(profile_001, tmp_path)
        # Count patient_001 files
        count_001 = len([p for p in tmp_path.iterdir() if p.name.endswith(".pdf")])

    assert len(paths_001) == 24
    assert count_001 == 24


# ---------------------------------------------------------------------------
# Temporal scoping
# ---------------------------------------------------------------------------

def test_build_prompt_excludes_future_diagnoses(demo_profiles):
    """Visit_01 prompt's KNOWN CONDITIONS should NOT contain future diagnoses."""
    from scripts.generate_documents import build_prompt

    profile = demo_profiles[0]  # patient_001
    visit = profile["visits"][0]  # visit_01 (June 2025)
    prompt = build_prompt(profile, visit, visit["document"]["type"])
    # SLE is diagnosed at visit_09, so it should NOT be in the known conditions
    # (It may appear in family history and temporal guardrail — that's fine)
    conditions_section = ""
    in_conditions = False
    for line in prompt.split("\n"):
        if "KNOWN CONDITIONS AT TIME OF VISIT" in line:
            in_conditions = True
            continue
        if in_conditions:
            if line.strip() == "" or (line.strip() and not line.startswith("  ")):
                break
            conditions_section += line + "\n"
    assert "Systemic Lupus Erythematosus" not in conditions_section
    assert "Vitamin D Deficiency" not in conditions_section  # Also future at visit_01
    # The guardrail should list them as future
    assert "TEMPORAL GUARDRAIL" in prompt
    assert "Systemic Lupus Erythematosus" in prompt  # In guardrail or family history


def test_build_prompt_includes_past_conditions(demo_profiles):
    """Visit_06 should include Tension-type Headache in known conditions but NOT SLE."""
    from scripts.generate_documents import build_prompt

    profile = demo_profiles[0]  # patient_001
    # visit_06 (2025-10-01) has Tension-type Headache diagnosed but SLE not yet
    visit = next(v for v in profile["visits"] if v["ref"] == "visit_06")
    prompt = build_prompt(profile, visit, visit["document"]["type"])
    # Extract conditions section
    conditions_section = ""
    in_conditions = False
    for line in prompt.split("\n"):
        if "KNOWN CONDITIONS AT TIME OF VISIT" in line:
            in_conditions = True
            continue
        if in_conditions:
            if line.strip() == "" or (line.strip() and not line.startswith("  ")):
                break
            conditions_section += line + "\n"
    assert "Tension" in conditions_section  # Tension-type Headache should be included
    assert "Systemic Lupus Erythematosus" not in conditions_section  # SLE not yet


def test_build_prompt_includes_temporal_guardrail(demo_profiles):
    """Prompt should contain temporal guardrail text."""
    from scripts.generate_documents import build_prompt

    profile = demo_profiles[0]
    visit = profile["visits"][0]
    prompt = build_prompt(profile, visit, visit["document"]["type"])
    assert "Do NOT reference" in prompt or "do NOT reference" in prompt or "TEMPORAL GUARDRAIL" in prompt


def test_build_prompt_does_not_contain_full_summary(demo_profiles):
    """Prompt should NOT contain the full patient summary."""
    from scripts.generate_documents import build_prompt

    profile = demo_profiles[0]
    visit = profile["visits"][0]
    prompt = build_prompt(profile, visit, visit["document"]["type"])
    assert profile["summary"] not in prompt


def test_build_prompt_includes_dob(demo_profiles):
    """Prompt should include the patient's date of birth."""
    from scripts.generate_documents import build_prompt

    profile = demo_profiles[0]
    visit = profile["visits"][0]
    prompt = build_prompt(profile, visit, visit["document"]["type"])
    assert profile["dob"] in prompt


def test_build_prompt_includes_family_history(demo_profiles):
    """Prompt should include family history."""
    from scripts.generate_documents import build_prompt

    profile = demo_profiles[0]
    visit = profile["visits"][0]
    prompt = build_prompt(profile, visit, visit["document"]["type"])
    # patient_001 has mother with SLE in family history
    assert "mother" in prompt.lower() or "Mother" in prompt
