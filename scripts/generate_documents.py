"""
Clinical document generator — uses Gemini 2.5 Flash to produce realistic
clinical document text from patient profiles, then renders to PDF.

Usage:
    python scripts/generate_documents.py [--patients patient_001 patient_006] [--output-dir data/pdfs]
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

load_dotenv()


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_DOC_TYPE_INSTRUCTIONS = {
    "intake_form": (
        "Generate a NEW PATIENT INTAKE FORM. Include: patient demographics, "
        "chief complaint, history of present illness, past medical history, "
        "family history, social history, review of systems, physical examination, "
        "assessment, and plan. Use standard clinical intake form formatting."
    ),
    "progress_note": (
        "Generate a clinical PROGRESS NOTE in SOAP format. Include: "
        "Subjective (patient-reported symptoms, changes since last visit), "
        "Objective (vitals, exam findings, lab results if available), "
        "Assessment (clinical interpretation, differential), "
        "Plan (orders, medication changes, follow-up). "
        "Use standard clinical documentation style."
    ),
    "lab_report": (
        "Generate a CLINICAL LABORATORY REPORT. Include: ordering provider, "
        "specimen collection date/time, test names with results, units, "
        "reference ranges, and abnormal flags. Add a brief interpretive comment "
        "from the reviewing pathologist/technologist. Use standard lab report formatting "
        "with aligned columns for results."
    ),
    "imaging_report": (
        "Generate a RADIOLOGY/IMAGING REPORT. Include: exam type, clinical indication, "
        "technique, comparison studies if applicable, detailed findings organized by "
        "anatomic region, and impression/conclusion. Use standard radiology report formatting."
    ),
    "discharge_summary": (
        "Generate a HOSPITAL DISCHARGE SUMMARY. Include: admission date, discharge date, "
        "admitting diagnosis, principal diagnosis, hospital course, significant findings, "
        "procedures performed, condition at discharge, discharge medications with instructions, "
        "follow-up appointments, and discharge instructions."
    ),
    "referral_letter": (
        "Generate a REFERRAL LETTER from one physician to another. Include: "
        "referring provider, receiving provider, reason for referral, relevant clinical history, "
        "pertinent exam findings, labs/imaging results, current medications, and specific "
        "questions or requests for the specialist. Use formal letter formatting."
    ),
    "consult_note": (
        "Generate a SPECIALIST CONSULTATION NOTE. Include: reason for consultation, "
        "history of present illness as gathered by the consultant, relevant past medical history, "
        "focused physical examination, review of outside records/labs, "
        "assessment/impression, and recommendations. Use standard consultation note formatting."
    ),
    "cdc_advisory": (
        "Generate a CDC CLINICAL ADVISORY DOCUMENT. Include: advisory title, "
        "classification of the condition, epidemiological summary, clinical features, "
        "diagnostic criteria, recommended laboratory workup, containment/isolation protocols, "
        "treatment considerations, and reporting requirements. Use formal public health document formatting."
    ),
}


def _get_visit_index(visits, visit_ref):
    """Return the index of a visit by its ref, or -1 if not found."""
    for i, v in enumerate(visits):
        if v["ref"] == visit_ref:
            return i
    return -1


def _conditions_as_of(profile, visit_ref):
    """Return conditions diagnosed at or before the given visit, excluding discoverable."""
    visits = profile["visits"]
    current_idx = _get_visit_index(visits, visit_ref)
    if current_idx < 0:
        return []
    result = []
    for cond in profile.get("conditions", []):
        if cond.get("discoverable", False):
            continue
        diag_visit = cond.get("diagnosed_visit")
        if diag_visit is None:
            result.append(cond)
        else:
            diag_idx = _get_visit_index(visits, diag_visit)
            if diag_idx >= 0 and diag_idx <= current_idx:
                result.append(cond)
    return result


def _medications_as_of(profile, visit_ref):
    """Return medications active at the given visit."""
    visits = profile["visits"]
    current_idx = _get_visit_index(visits, visit_ref)
    if current_idx < 0:
        return []
    result = []
    for med in profile.get("medications", []):
        start_idx = _get_visit_index(visits, med.get("start_visit", ""))
        if start_idx < 0 or start_idx > current_idx:
            continue
        end_visit = med.get("end_visit")
        if end_visit:
            end_idx = _get_visit_index(visits, end_visit)
            if end_idx >= 0 and end_idx < current_idx:
                continue
        result.append(med)
    return result


def _future_diagnoses(profile, visit_ref):
    """Return names of conditions diagnosed after the given visit."""
    visits = profile["visits"]
    current_idx = _get_visit_index(visits, visit_ref)
    if current_idx < 0:
        return []
    result = []
    for cond in profile.get("conditions", []):
        diag_visit = cond.get("diagnosed_visit")
        if diag_visit:
            diag_idx = _get_visit_index(visits, diag_visit)
            if diag_idx >= 0 and diag_idx > current_idx:
                result.append(cond["name"])
    return result


def build_prompt(profile: dict, visit: dict, doc_type: str) -> str:
    """Build a Gemini prompt for generating a clinical document.

    Uses temporal scoping: only conditions/medications known at the time
    of the visit are included. Future diagnoses are explicitly excluded
    via a temporal guardrail.
    """
    instructions = _DOC_TYPE_INSTRUCTIONS.get(doc_type, _DOC_TYPE_INSTRUCTIONS["progress_note"])
    visit_ref = visit["ref"]

    parts = [
        "You are an expert clinical documentation specialist. Generate a realistic, "
        "detailed clinical document based on the following patient information and visit context.\n",
        f"DOCUMENT TYPE INSTRUCTIONS:\n{instructions}\n",
        f"PATIENT: {profile['name']}, {profile['age']}-year-old {profile['sex']}",
        f"MRN: {profile['mrn']}",
        f"DATE OF BIRTH: {profile.get('dob', 'Unknown')}\n",
    ]

    # Temporally-scoped conditions
    known_conditions = _conditions_as_of(profile, visit_ref)
    if known_conditions:
        parts.append("KNOWN CONDITIONS AT TIME OF VISIT:")
        for cond in known_conditions:
            parts.append(f"  - {cond['name']} ({cond.get('icd_code', '')}) — {cond['status']}")
        parts.append("")
    else:
        parts.append("KNOWN CONDITIONS AT TIME OF VISIT: None\n")

    # Temporally-scoped medications
    active_meds = _medications_as_of(profile, visit_ref)
    if active_meds:
        parts.append("CURRENT MEDICATIONS AT TIME OF VISIT:")
        for med in active_meds:
            parts.append(f"  - {med['name']} {med['dosage']} {med['frequency']}")
        parts.append("")
    else:
        parts.append("CURRENT MEDICATIONS AT TIME OF VISIT: None\n")

    # Family history (static, always included)
    family_hx = profile.get("family_history", [])
    if family_hx:
        parts.append("FAMILY HISTORY:")
        for fh in family_hx:
            age_str = f", diagnosed age {fh['diagnosed_age']}" if fh.get("diagnosed_age") else ""
            parts.append(f"  - {fh['relation'].title()}: {fh['condition']}{age_str}")
        parts.append("")

    # Temporal guardrail
    future_dx = _future_diagnoses(profile, visit_ref)
    if future_dx:
        parts.append(f"TEMPORAL GUARDRAIL: This document is written on {visit['date']}. "
                      f"Do NOT reference, mention, or hint at the following diagnoses that "
                      f"have NOT yet been made: {', '.join(future_dx)}. The clinician does "
                      f"not yet know about these conditions.\n")

    parts.extend([
        f"VISIT DATE: {visit['date']}",
        f"VISIT TYPE: {visit['type']}",
        f"PROVIDER: {visit['provider']}",
        f"CHIEF COMPLAINT: {visit['chief_complaint']}\n",
        f"CLINICAL NARRATIVE:\n{visit['narrative']}\n",
    ])

    # Include labs if present
    labs = visit.get("labs", [])
    if labs:
        parts.append("LABORATORY RESULTS:")
        for lab in labs:
            flag_str = f" [{lab['flag'].upper()}]" if lab["flag"] != "normal" else ""
            parts.append(f"  - {lab['test']}: {lab['value']} {lab['unit']} (ref: {lab['range']}){flag_str}")
        parts.append("")

    # Include procedures if present
    procedures = visit.get("procedures", [])
    if procedures:
        parts.append("PROCEDURES:")
        for proc in procedures:
            parts.append(f"  - {proc['name']}: {proc['outcome']}")
        parts.append("")

    # Include medications started/discontinued
    meds_started = visit.get("medications_started", [])
    if meds_started:
        parts.append(f"MEDICATIONS STARTED: {', '.join(meds_started)}")

    meds_discontinued = visit.get("medications_discontinued", [])
    if meds_discontinued:
        parts.append(f"MEDICATIONS DISCONTINUED: {', '.join(meds_discontinued)}")

    # Include referrals
    referrals = visit.get("referrals", [])
    if referrals:
        parts.append("REFERRALS:")
        for ref in referrals:
            parts.append(f"  - To: {ref['to']} — {ref['reason']}")

    parts.append(
        "\nGenerate the complete document text. Use realistic clinical language, "
        "appropriate medical terminology, and standard formatting for this document type. "
        "Do not include any markdown formatting. Output plain text only."
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Gemini API (REST, no SDK needed)
# ---------------------------------------------------------------------------

_GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
_MAX_RETRIES = 3


def call_gemini(prompt: str) -> str:
    """Call Gemini 2.5 Flash via REST API. Returns generated text."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY not set in environment")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 4096,
        },
    }

    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.post(
                f"{_GEMINI_API_URL}?key={api_key}",
                json=payload,
                timeout=60,
            )
            if resp.status_code == 429:
                wait = 2 ** attempt
                print(f"  Rate limited, retrying in {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (requests.RequestException, KeyError, IndexError) as e:
            if attempt < _MAX_RETRIES - 1:
                wait = 2 ** attempt
                print(f"  Error: {e}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise RuntimeError(f"Gemini API failed after {_MAX_RETRIES} attempts: {e}")

    raise RuntimeError("Gemini API failed: exhausted retries")


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------

def text_to_pdf(text: str, filename: str, output_dir: Path, header: dict) -> Path:
    """Render clinical text to a PDF with header block."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename

    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    header_style = ParagraphStyle(
        "DocHeader",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=2,
    )
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading2"],
        fontSize=14,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "DocBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        spaceAfter=4,
    )

    story = []

    # Header block
    doc_type_display = header.get("doc_type", "Clinical Document")
    story.append(Paragraph(f"<b>{doc_type_display.upper()}</b>", title_style))
    story.append(Paragraph(f"<b>Patient:</b> {header.get('patient_name', '')}", header_style))
    story.append(Paragraph(f"<b>MRN:</b> {header.get('mrn', '')}", header_style))
    story.append(Paragraph(f"<b>Date:</b> {header.get('date', '')}", header_style))
    story.append(Paragraph(f"<b>Provider:</b> {header.get('provider', '')}", header_style))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1, color="black"))
    story.append(Spacer(1, 12))

    # Body — split by paragraphs
    for para_text in text.split("\n\n"):
        para_text = para_text.strip()
        if not para_text:
            continue
        # Handle single newlines within paragraphs
        para_text = para_text.replace("\n", "<br/>")
        # Escape XML special chars that aren't our <br/>
        safe_text = para_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Restore our <br/> tags
        safe_text = safe_text.replace("&lt;br/&gt;", "<br/>")
        story.append(Paragraph(safe_text, body_style))
        story.append(Spacer(1, 6))

    doc.build(story)
    return path


# ---------------------------------------------------------------------------
# Document generation orchestration
# ---------------------------------------------------------------------------

_DOC_TYPE_DISPLAY = {
    "intake_form": "Intake Form",
    "progress_note": "Progress Note",
    "lab_report": "Laboratory Report",
    "imaging_report": "Imaging Report",
    "discharge_summary": "Discharge Summary",
    "referral_letter": "Referral Letter",
    "consult_note": "Consultation Note",
    "cdc_advisory": "CDC Advisory",
}


def generate_visit_document(
    profile: dict,
    visit: dict,
    output_dir: Path,
    *,
    doc_key: str = "document",
) -> Path | None:
    """Generate a single PDF for a visit's document (or labs_document).

    Returns the path to the PDF, or None if doc_key doesn't exist on the visit.
    Skips generation if the file already exists (idempotent).
    """
    doc_info = visit.get(doc_key)
    if not doc_info:
        return None

    filename = doc_info["filename"]
    target = output_dir / filename

    # Idempotent: skip if already exists
    if target.exists():
        return target

    doc_type = doc_info["type"]
    prompt = build_prompt(profile, visit, doc_type)
    text = call_gemini(prompt)

    header = {
        "patient_name": profile["name"],
        "mrn": profile["mrn"],
        "date": visit["date"],
        "doc_type": _DOC_TYPE_DISPLAY.get(doc_type, doc_type.replace("_", " ").title()),
        "provider": visit["provider"],
    }

    return text_to_pdf(text, filename, output_dir, header)


def generate_documents_for_patient(profile: dict, output_dir: Path) -> list[Path]:
    """Generate all PDFs for a patient. Returns list of created paths."""
    paths = []
    total = sum(1 + (1 if v.get("labs_document") else 0) for v in profile["visits"])

    for i, visit in enumerate(profile["visits"], 1):
        # Main visit document
        print(f"  [{i}/{total}] {visit['document']['filename']}...")
        path = generate_visit_document(profile, visit, output_dir, doc_key="document")
        if path:
            paths.append(path)

        # Separate lab report document (if exists)
        if visit.get("labs_document"):
            print(f"  [{i}/{total}] {visit['labs_document']['filename']}...")
            lab_path = generate_visit_document(profile, visit, output_dir, doc_key="labs_document")
            if lab_path:
                paths.append(lab_path)

    return paths


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate clinical PDFs from patient profiles")
    parser.add_argument(
        "--patients",
        nargs="*",
        help="Patient IDs to generate for (default: all)",
    )
    parser.add_argument(
        "--patients-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "patients",
        help="Directory containing patient_*.json files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "pdfs",
        help="Output directory for generated PDFs",
    )
    args = parser.parse_args()

    # Load profiles
    profiles = []
    for path in sorted(args.patients_dir.glob("patient_*.json")):
        with open(path) as f:
            profile = json.load(f)
        if args.patients and profile["id"] not in args.patients:
            continue
        profiles.append(profile)

    if not profiles:
        print(f"No matching profiles found in {args.patients_dir}")
        return

    print(f"Generating documents for {len(profiles)} patient(s)...")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    total_paths = []
    for profile in profiles:
        print(f"\n{profile['name']} ({profile['id']}):")
        paths = generate_documents_for_patient(profile, args.output_dir)
        total_paths.extend(paths)

    print(f"\nDone! Generated {len(total_paths)} PDFs in {args.output_dir}")


if __name__ == "__main__":
    main()
