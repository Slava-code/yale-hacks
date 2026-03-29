#!/usr/bin/env python3
"""Generate patient profiles using Gemini 2.5 Flash API.

Reads SCHEMA.md and an example profile, then generates ~35 new patient profiles
via the Gemini API. Saves each to data/patients/patient_NNN.json.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# --- Paths ---
ROOT = Path(__file__).resolve().parent.parent
# Try worktree .env first, then main repo .env
ENV_PATHS = [
    ROOT / ".env",
    ROOT.parent.parent.parent.parent / ".env",  # main repo root if running from worktree
]
PATIENTS_DIR = ROOT / "data" / "patients"
SCHEMA_PATH = PATIENTS_DIR / "SCHEMA.md"
EXAMPLE_PATH = PATIENTS_DIR / "patient_001.json"


def load_env():
    """Parse .env file and return dict of key=value pairs."""
    for env_path in ENV_PATHS:
        if env_path.exists():
            result = {}
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    result[key.strip()] = value.strip()
            return result
    return {}


def call_gemini(api_key: str, prompt: str, retries: int = 3) -> dict:
    """Call Gemini 2.5 Flash API and return parsed JSON response."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 1.0,
            "maxOutputTokens": 65536,
            "responseMimeType": "application/json",
        },
    }
    data = json.dumps(payload).encode()

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            profile = json.loads(text)
            return profile
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"    API error (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"    Parse error (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def validate_profile(profile: dict, patient_id: str, tier: str) -> list[str]:
    """Validate a generated profile. Returns list of error strings."""
    errors = []
    required = {"id", "name", "age", "sex", "mrn", "tier", "summary",
                "conditions", "medications", "providers", "visits"}

    if not isinstance(profile, dict):
        return ["Profile is not a JSON object"]

    missing = required - set(profile.keys())
    if missing:
        errors.append(f"Missing fields: {missing}")

    if profile.get("id") != patient_id:
        errors.append(f"id should be '{patient_id}', got '{profile.get('id')}'")

    if profile.get("tier") != tier:
        errors.append(f"tier should be '{tier}', got '{profile.get('tier')}'")

    if profile.get("sex") not in ("male", "female"):
        errors.append(f"sex must be 'male' or 'female', got '{profile.get('sex')}'")

    mrn = profile.get("mrn", "")
    if not mrn.startswith("MRN-") or len(mrn) != 9:
        errors.append(f"MRN format invalid: '{mrn}'")

    # Validate conditions
    for cond in profile.get("conditions", []):
        if not cond.get("icd_code"):
            errors.append(f"Condition '{cond.get('name', '?')}' missing icd_code")
        if cond.get("status") not in ("active", "resolved", "chronic"):
            errors.append(f"Condition '{cond.get('name', '?')}' invalid status: '{cond.get('status')}'")

    # Validate medications
    med_names = {m["name"] for m in profile.get("medications", []) if "name" in m}
    for med in profile.get("medications", []):
        if med.get("status") not in ("active", "discontinued"):
            errors.append(f"Medication '{med.get('name', '?')}' invalid status: '{med.get('status')}'")

    # Validate providers
    provider_names = {p["name"] for p in profile.get("providers", []) if "name" in p}

    # Validate visits
    visit_refs = []
    visit_dates = []
    for visit in profile.get("visits", []):
        ref = visit.get("ref", "")
        visit_refs.append(ref)
        visit_dates.append(visit.get("date", ""))

        if visit.get("type") not in ("initial", "follow-up", "emergency", "routine", "consult"):
            errors.append(f"Visit {ref}: invalid type '{visit.get('type')}'")

        if visit.get("provider") not in provider_names:
            errors.append(f"Visit {ref}: provider '{visit.get('provider')}' not in providers")

        # Check document
        doc = visit.get("document")
        if not doc or not doc.get("filename"):
            errors.append(f"Visit {ref}: missing document/filename")
        elif doc:
            import re
            pattern = r"^[a-z_]+_[a-z]+_\d{4}_[a-z]{3}(_\d+)?\.pdf$"
            if not re.match(pattern, doc["filename"]):
                errors.append(f"Visit {ref}: bad filename '{doc['filename']}'")

        # Check labs_document if present
        labs_doc = visit.get("labs_document")
        if labs_doc:
            import re
            pattern = r"^[a-z_]+_[a-z]+_\d{4}_[a-z]{3}(_\d+)?\.pdf$"
            if not re.match(pattern, labs_doc.get("filename", "")):
                errors.append(f"Visit {ref}: bad labs filename '{labs_doc.get('filename', '')}'")

        # Check medication references
        for med in visit.get("medications_started", []):
            if med not in med_names:
                errors.append(f"Visit {ref}: medications_started '{med}' not in medications")
        for med in visit.get("medications_discontinued", []):
            if med not in med_names:
                errors.append(f"Visit {ref}: medications_discontinued '{med}' not in medications")

        # Check referral references
        for referral in visit.get("referrals", []):
            if referral.get("to") not in provider_names:
                errors.append(f"Visit {ref}: referral to '{referral.get('to')}' not in providers")

        # Check lab entries
        for lab in visit.get("labs", []):
            if lab.get("flag") not in ("normal", "high", "low", "critical"):
                errors.append(f"Visit {ref}: lab '{lab.get('test', '?')}' bad flag '{lab.get('flag')}'")

    # Check unique refs
    dupes = [r for r in visit_refs if visit_refs.count(r) > 1]
    if dupes:
        errors.append(f"Duplicate visit refs: {set(dupes)}")

    # Check chronological order
    if visit_dates != sorted(visit_dates):
        errors.append("Visits not in chronological order")

    # Tier-specific checks
    if tier in ("demo", "complex"):
        if not profile.get("storyline"):
            errors.append(f"{tier} tier requires a storyline")
        if len(profile.get("visits", [])) < 15:
            errors.append(f"{tier} tier requires >= 15 visits, got {len(profile.get('visits', []))}")

    if tier == "moderate":
        nv = len(profile.get("visits", []))
        if nv < 5 or nv > 10:
            errors.append(f"moderate tier should have 5-10 visits, got {nv}")

    if tier == "simple":
        nv = len(profile.get("visits", []))
        if nv < 2 or nv > 3:
            errors.append(f"simple tier should have 2-3 visits, got {nv}")

    return errors


def fix_profile(profile: dict, patient_id: str, tier: str, expected_name: str = None, expected_mrn: str = None) -> dict:
    """Apply automatic fixes to common Gemini issues."""
    # Fix id and tier
    profile["id"] = patient_id
    profile["tier"] = tier

    if expected_name:
        profile["name"] = expected_name
    if expected_mrn:
        profile["mrn"] = expected_mrn

    # Ensure MRN format
    mrn = profile.get("mrn", "")
    if not mrn.startswith("MRN-") or len(mrn) != 9:
        # Generate a random MRN
        import random
        profile["mrn"] = f"MRN-{random.randint(10000, 99999):05d}"

    # Fix visit dates to be chronological
    visits = profile.get("visits", [])
    dates = [v.get("date", "") for v in visits]
    if dates != sorted(dates):
        sorted_dates = sorted(dates)
        for i, visit in enumerate(visits):
            visit["date"] = sorted_dates[i]

    # Fix provider references
    provider_names = {p["name"] for p in profile.get("providers", [])}
    for visit in visits:
        if visit.get("provider") not in provider_names and provider_names:
            # Assign first provider if reference is broken
            visit["provider"] = list(provider_names)[0]
        for referral in visit.get("referrals", []):
            if referral.get("to") not in provider_names and len(provider_names) > 1:
                referral["to"] = list(provider_names)[1]

    # Fix medication references
    med_names = {m["name"] for m in profile.get("medications", [])}
    for visit in visits:
        visit["medications_started"] = [
            m for m in visit.get("medications_started", []) if m in med_names
        ]
        visit["medications_discontinued"] = [
            m for m in visit.get("medications_discontinued", []) if m in med_names
        ]
        # Remove empty lists
        if not visit.get("medications_started"):
            visit.pop("medications_started", None)
        if not visit.get("medications_discontinued"):
            visit.pop("medications_discontinued", None)

    # Fix document filenames
    import re
    pattern = re.compile(r"^[a-z_]+_[a-z]+_\d{4}_[a-z]{3}(_\d+)?\.pdf$")
    lastname = profile.get("name", "unknown").split()[-1].lower()

    for visit in visits:
        doc = visit.get("document")
        if doc:
            fname = doc.get("filename", "")
            if not pattern.match(fname):
                # Rebuild filename from type and visit date
                doc_type = doc.get("type", "progress_note")
                date = visit.get("date", "2025-01-01")
                year = date[:4]
                month_num = int(date[5:7])
                month_abbr = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"][month_num - 1]
                doc["filename"] = f"{doc_type}_{lastname}_{year}_{month_abbr}.pdf"

        labs_doc = visit.get("labs_document")
        if labs_doc:
            fname = labs_doc.get("filename", "")
            if not pattern.match(fname):
                date = visit.get("date", "2025-01-01")
                year = date[:4]
                month_num = int(date[5:7])
                month_abbr = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"][month_num - 1]
                labs_doc["filename"] = f"lab_report_{lastname}_{year}_{month_abbr}.pdf"

    # Deduplicate filenames within same type+month by adding suffixes
    seen_filenames = {}
    for visit in visits:
        for doc_key in ["document", "labs_document"]:
            doc = visit.get(doc_key)
            if not doc:
                continue
            fname = doc["filename"]
            base = fname.replace(".pdf", "")
            # Strip existing suffix like _2, _3
            base_clean = re.sub(r"_\d+$", "", base)
            if base_clean in seen_filenames:
                seen_filenames[base_clean] += 1
                doc["filename"] = f"{base_clean}_{seen_filenames[base_clean]}.pdf"
            else:
                seen_filenames[base_clean] = 1
                # First occurrence keeps original name (no suffix)
                doc["filename"] = f"{base_clean}.pdf"

    # Fix condition statuses
    valid_cond_statuses = {"active", "resolved", "chronic"}
    for cond in profile.get("conditions", []):
        if cond.get("status") not in valid_cond_statuses:
            cond["status"] = "active"

    # Fix medication statuses
    valid_med_statuses = {"active", "discontinued"}
    for med in profile.get("medications", []):
        if med.get("status") not in valid_med_statuses:
            med["status"] = "active"

    # Fix visit types
    valid_types = {"initial", "follow-up", "emergency", "routine", "consult"}
    for visit in visits:
        if visit.get("type") not in valid_types:
            visit["type"] = "follow-up"

    # Fix lab flags
    valid_flags = {"normal", "high", "low", "critical"}
    for visit in visits:
        for lab in visit.get("labs", []):
            if lab.get("flag") not in valid_flags:
                lab["flag"] = "normal"

    # Ensure unique visit refs
    seen_refs = set()
    for i, visit in enumerate(visits):
        ref = visit.get("ref", f"visit_{i+1:02d}")
        if ref in seen_refs:
            ref = f"visit_{i+1:02d}"
        visit["ref"] = ref
        seen_refs.add(ref)

    return profile


# --- Patient definitions ---

STUB_PATIENTS = [
    {
        "patient_id": "patient_002",
        "name": "Maria Garcia",
        "age": 58,
        "sex": "female",
        "mrn": "MRN-41092",
        "tier": "moderate",
        "conditions_hint": "Type 2 Diabetes Mellitus (E11.9) and Essential Hypertension (I10), well-controlled on Metformin and Lisinopril",
        "storyline_hint": "58-year-old woman with longstanding diabetes and hypertension, managed by endocrinology with routine follow-ups over 2 years. HbA1c fluctuates between 6.5-7.8%, blood pressure gradually optimized.",
        "visits_target": 7,
    },
    {
        "patient_id": "patient_003",
        "name": "David Chen",
        "age": 45,
        "sex": "male",
        "mrn": "MRN-55671",
        "tier": "moderate",
        "conditions_hint": "ST-Elevation Myocardial Infarction (I21.0) — acute STEMI, presented with chest pain radiating to left arm, treated with PCI and drug-eluting stent",
        "storyline_hint": "45-year-old man presents to ED with acute chest pain, diagnosed with STEMI, undergoes emergency PCI, then followed by cardiology for cardiac rehab over 6 months.",
        "visits_target": 7,
    },
    {
        "patient_id": "patient_004",
        "name": "Sarah Johnson",
        "age": 27,
        "sex": "female",
        "mrn": "MRN-33890",
        "tier": "simple",
        "conditions_hint": "Iron Deficiency Anemia (D50.9) — presenting with fatigue, pallor",
        "storyline_hint": "",
        "visits_target": 3,
    },
    {
        "patient_id": "patient_005",
        "name": "Robert Williams",
        "age": 72,
        "sex": "male",
        "mrn": "MRN-62417",
        "tier": "simple",
        "conditions_hint": "Chronic Obstructive Pulmonary Disease (J44.1) — on home oxygen, history of recurrent pneumonia",
        "storyline_hint": "",
        "visits_target": 3,
    },
]

COMPLEX_PATIENTS = [
    {
        "patient_id": "patient_007",
        "name": "Elena Vasquez",
        "age": 64,
        "sex": "female",
        "tier": "complex",
        "conditions_hint": "Chronic Kidney Disease Stage 4 (N18.4) progressing toward dialysis, with secondary hyperparathyroidism and anemia of chronic disease. Also has Type 2 Diabetes (E11.9).",
        "storyline_hint": "3-year progression of CKD from stage 3 to 4. Multiple nephrology visits, erythropoietin started, phosphate binders added. Dialysis access surgery planned. Secondary complications managed simultaneously.",
        "visits_target": 18,
    },
    {
        "patient_id": "patient_008",
        "name": "James Okafor",
        "age": 52,
        "sex": "male",
        "tier": "complex",
        "conditions_hint": "Heart Failure with Reduced Ejection Fraction (I50.20), Atrial Fibrillation (I48.91), and Chronic Kidney Disease Stage 3 (N18.3). Multiple medication adjustments.",
        "storyline_hint": "Progressive heart failure over 2 years with declining EF from 40% to 25%. Multiple medication titrations (beta-blocker, ACE-I, spironolactone). A-fib develops, anticoagulation started. Hospitalized twice for decompensation. CKD complicates diuretic dosing.",
        "visits_target": 18,
    },
    {
        "patient_id": "patient_009",
        "name": "Priya Sharma",
        "age": 38,
        "sex": "female",
        "tier": "complex",
        "conditions_hint": "Multiple Sclerosis, Relapsing-Remitting (G35), Depression (F32.1), and Vitamin D Deficiency (E55.9). Started on disease-modifying therapy.",
        "storyline_hint": "Initial presentation with optic neuritis, MRI reveals demyelinating lesions. Lumbar puncture confirms oligoclonal bands. Started on interferon beta-1a, then switched to fingolimod after relapse. Depression develops during treatment course. Physical therapy referrals.",
        "visits_target": 17,
    },
    {
        "patient_id": "patient_010",
        "name": "William Thompson",
        "age": 68,
        "sex": "male",
        "tier": "complex",
        "conditions_hint": "Non-Small Cell Lung Cancer Stage IIIA (C34.1), COPD (J44.1), and Pulmonary Embolism (I26.99). On chemotherapy and anticoagulation.",
        "storyline_hint": "Incidental lung mass found on chest CT for COPD exacerbation. Biopsy confirms NSCLC adenocarcinoma. Staged IIIA. Chemoradiation started. Develops PE during treatment, anticoagulation initiated. Multiple oncology, pulmonology, and radiation oncology visits.",
        "visits_target": 18,
    },
    {
        "patient_id": "patient_011",
        "name": "Fatima Al-Hassan",
        "age": 44,
        "sex": "female",
        "tier": "complex",
        "conditions_hint": "Crohn's Disease (K50.90) with stricturing behavior, Iron Deficiency Anemia (D50.9), and Osteoporosis (M81.0) secondary to chronic corticosteroid use.",
        "storyline_hint": "Longstanding Crohn's with multiple flares. Initially on mesalamine, escalated to azathioprine, then infliximab after stricture found on MR enterography. Small bowel resection performed. Post-op complications. DEXA scan reveals osteoporosis from years of prednisone.",
        "visits_target": 17,
    },
    {
        "patient_id": "patient_012",
        "name": "Raymond Jackson",
        "age": 75,
        "sex": "male",
        "tier": "complex",
        "conditions_hint": "Parkinson's Disease (G20), Orthostatic Hypotension (I95.1), and Major Depressive Disorder (F33.1). Progressive neurological decline over 3 years.",
        "storyline_hint": "Initial presentation with resting tremor and bradykinesia. Gradual medication titration with carbidopa-levetiracetam. Develops wearing-off phenomenon. Orthostatic hypotension complicates management. Depression emerges as disease progresses. Physical therapy, occupational therapy, speech therapy referrals over time.",
        "visits_target": 16,
    },
    {
        "patient_id": "patient_013",
        "name": "Anika Patel",
        "age": 33,
        "sex": "female",
        "tier": "complex",
        "conditions_hint": "Graves' Disease (E05.00) with thyroid eye disease (H06.21), subsequent hypothyroidism (E03.9) post-radioactive iodine treatment, and Anxiety Disorder (F41.1).",
        "storyline_hint": "Presents with weight loss, tachycardia, tremor. Labs confirm hyperthyroidism with positive TSI. Started on methimazole, develops agranulocytosis. Switched to radioactive iodine ablation. Subsequently becomes hypothyroid. Thyroid eye disease worsens requiring ophthalmology co-management. Anxiety predates thyroid diagnosis.",
        "visits_target": 16,
    },
    {
        "patient_id": "patient_014",
        "name": "Carlos Rivera",
        "age": 59,
        "sex": "male",
        "tier": "complex",
        "conditions_hint": "Cirrhosis secondary to Alcohol-Related Liver Disease (K70.30), Esophageal Varices (I85.00), and Hepatic Encephalopathy (K72.90). On transplant waiting list.",
        "storyline_hint": "History of heavy alcohol use. Presents with jaundice and ascites. Workup reveals cirrhosis with portal hypertension. EGD finds grade 2 esophageal varices, banded. Develops hepatic encephalopathy episodes. MELD score monitored. Evaluated for transplant candidacy. Must demonstrate 6 months sobriety.",
        "visits_target": 17,
    },
]

MODERATE_PATIENTS = [
    {
        "patient_id": "patient_015",
        "name": "Linda Morrison",
        "age": 55,
        "sex": "female",
        "tier": "moderate",
        "conditions_hint": "Major Depressive Disorder (F33.1), Generalized Anxiety Disorder (F41.1). SSRI management over 1 year.",
        "visits_target": 7,
    },
    {
        "patient_id": "patient_016",
        "name": "Ahmed Hassan",
        "age": 62,
        "sex": "male",
        "tier": "moderate",
        "conditions_hint": "Gout (M10.9) and Chronic Kidney Disease Stage 2 (N18.2). Recurrent gout flares.",
        "visits_target": 6,
    },
    {
        "patient_id": "patient_017",
        "name": "Jessica Wu",
        "age": 34,
        "sex": "female",
        "tier": "moderate",
        "conditions_hint": "Gestational Diabetes (O24.419) and Preeclampsia (O14.10). Managed through pregnancy.",
        "visits_target": 8,
    },
    {
        "patient_id": "patient_018",
        "name": "Thomas Oduya",
        "age": 48,
        "sex": "male",
        "tier": "moderate",
        "conditions_hint": "Obstructive Sleep Apnea (G47.33) and Obesity (E66.01). CPAP titration and weight management.",
        "visits_target": 6,
    },
    {
        "patient_id": "patient_019",
        "name": "Margaret Kelly",
        "age": 71,
        "sex": "female",
        "tier": "moderate",
        "conditions_hint": "Osteoarthritis of bilateral knees (M17.0) and Essential Hypertension (I10). Joint replacement evaluation.",
        "visits_target": 7,
    },
    {
        "patient_id": "patient_020",
        "name": "Kenji Tanaka",
        "age": 40,
        "sex": "male",
        "tier": "moderate",
        "conditions_hint": "Ulcerative Colitis (K51.90) and Iron Deficiency Anemia (D50.9). Flare management with mesalamine.",
        "visits_target": 7,
    },
    {
        "patient_id": "patient_021",
        "name": "Sophia Petrov",
        "age": 29,
        "sex": "female",
        "tier": "moderate",
        "conditions_hint": "Migraine with Aura (G43.1) and Anxiety Disorder (F41.1). Preventive therapy with topiramate.",
        "visits_target": 6,
    },
    {
        "patient_id": "patient_022",
        "name": "Derek Washington",
        "age": 66,
        "sex": "male",
        "tier": "moderate",
        "conditions_hint": "Type 2 Diabetes Mellitus (E11.9) with Diabetic Peripheral Neuropathy (G63). Insulin initiation.",
        "visits_target": 8,
    },
    {
        "patient_id": "patient_023",
        "name": "Irene Nakamura",
        "age": 53,
        "sex": "female",
        "tier": "moderate",
        "conditions_hint": "Hypothyroidism (E03.9) and Hyperlipidemia (E78.5). Levothyroxine and statin management.",
        "visits_target": 6,
    },
    {
        "patient_id": "patient_024",
        "name": "Marcus Brown",
        "age": 37,
        "sex": "male",
        "tier": "moderate",
        "conditions_hint": "Asthma, Moderate Persistent (J45.40) and Allergic Rhinitis (J30.9). Step-up therapy with inhaled corticosteroids.",
        "visits_target": 6,
    },
    {
        "patient_id": "patient_025",
        "name": "Olga Federova",
        "age": 60,
        "sex": "female",
        "tier": "moderate",
        "conditions_hint": "Rheumatoid Arthritis (M06.9) and Osteoporosis (M81.0). Methotrexate started, DEXA monitoring.",
        "visits_target": 7,
    },
]

SIMPLE_PATIENTS = [
    {"patient_id": "patient_026", "name": "Ryan Mitchell", "age": 22, "sex": "male", "tier": "simple", "conditions_hint": "Acute Bronchitis (J20.9). Single episode, symptomatic treatment.", "visits_target": 2},
    {"patient_id": "patient_027", "name": "Hannah Lewis", "age": 31, "sex": "female", "tier": "simple", "conditions_hint": "Urinary Tract Infection (N39.0). Uncomplicated, treated with antibiotics.", "visits_target": 2},
    {"patient_id": "patient_028", "name": "Victor Gomez", "age": 45, "sex": "male", "tier": "simple", "conditions_hint": "Acute Low Back Pain (M54.5). Musculoskeletal strain, conservative management.", "visits_target": 2},
    {"patient_id": "patient_029", "name": "Claire Dubois", "age": 28, "sex": "female", "tier": "simple", "conditions_hint": "Contact Dermatitis (L25.9). Allergic reaction to new detergent, topical steroids.", "visits_target": 2},
    {"patient_id": "patient_030", "name": "Samuel Nkomo", "age": 56, "sex": "male", "tier": "simple", "conditions_hint": "Benign Paroxysmal Positional Vertigo (H81.10). Epley maneuver performed.", "visits_target": 2},
    {"patient_id": "patient_031", "name": "Emily Carter", "age": 35, "sex": "female", "tier": "simple", "conditions_hint": "Acute Sinusitis (J01.90). Viral, symptomatic treatment only.", "visits_target": 2},
    {"patient_id": "patient_032", "name": "Dmitri Volkov", "age": 42, "sex": "male", "tier": "simple", "conditions_hint": "Lateral Epicondylitis — Tennis Elbow (M77.10). Physical therapy referral.", "visits_target": 3},
    {"patient_id": "patient_033", "name": "Amara Diallo", "age": 25, "sex": "female", "tier": "simple", "conditions_hint": "Acute Gastroenteritis (K52.9). Viral, hydration management.", "visits_target": 2},
    {"patient_id": "patient_034", "name": "Patrick O'Brien", "age": 67, "sex": "male", "tier": "simple", "conditions_hint": "Seborrheic Keratosis (L82.1). Benign skin lesion, reassurance and monitoring.", "visits_target": 2},
    {"patient_id": "patient_035", "name": "Mei-Lin Chang", "age": 39, "sex": "female", "tier": "simple", "conditions_hint": "Carpal Tunnel Syndrome (G56.00). Wrist splinting, nerve conduction study.", "visits_target": 3},
    {"patient_id": "patient_036", "name": "Antoine Rousseau", "age": 50, "sex": "male", "tier": "simple", "conditions_hint": "Acute Conjunctivitis (H10.9). Bacterial, treated with antibiotic eye drops.", "visits_target": 2},
    {"patient_id": "patient_037", "name": "Grace Adeyemi", "age": 33, "sex": "female", "tier": "simple", "conditions_hint": "Plantar Fasciitis (M72.2). Conservative treatment with stretching exercises.", "visits_target": 2},
    {"patient_id": "patient_038", "name": "Daniel Eriksson", "age": 58, "sex": "male", "tier": "simple", "conditions_hint": "Vitamin B12 Deficiency (E53.8). Oral supplementation started.", "visits_target": 2},
    {"patient_id": "patient_039", "name": "Yuki Watanabe", "age": 26, "sex": "female", "tier": "simple", "conditions_hint": "Acute Pharyngitis (J02.9). Strep test negative, symptomatic care.", "visits_target": 2},
    {"patient_id": "patient_040", "name": "Howard Chen", "age": 73, "sex": "male", "tier": "simple", "conditions_hint": "Herpes Zoster — Shingles (B02.9). Antiviral treatment with valacyclovir.", "visits_target": 3},
]


def build_prompt(schema_content: str, example_json: str, patient_def: dict) -> str:
    """Build the Gemini prompt for a patient."""
    patient_id = patient_def["patient_id"]
    name = patient_def["name"]
    age = patient_def["age"]
    sex = patient_def["sex"]
    tier = patient_def["tier"]
    mrn = patient_def.get("mrn", "")
    conditions_hint = patient_def["conditions_hint"]
    storyline_hint = patient_def.get("storyline_hint", "")
    visits_target = patient_def["visits_target"]
    lastname = name.split()[-1].lower()

    mrn_instruction = f'Use exactly this MRN: "{mrn}"' if mrn else 'Generate a unique MRN in format MRN-NNNNN (5 digits). Do NOT use any of these existing MRNs: MRN-78234, MRN-41092, MRN-55671, MRN-33890, MRN-62417, MRN-91447'

    tier_instructions = ""
    if tier in ("demo", "complex"):
        tier_instructions = f"""- This is a {tier}-tier patient. You MUST include a "storyline" field with a detailed narrative arc.
- You MUST generate at least 15 visits (target: {visits_target}).
- Include rich clinical detail: labs with specific values, procedures, referrals, medication changes."""
    elif tier == "moderate":
        tier_instructions = f"""- This is a moderate-tier patient. The "storyline" field is optional.
- Generate exactly {visits_target} visits (must be between 5 and 10).
- Include some labs, at least one medication, and a clear clinical narrative."""
    elif tier == "simple":
        tier_instructions = f"""- This is a simple-tier patient. The "storyline" field is optional (omit it or leave empty).
- Generate exactly {visits_target} visits (must be 2 or 3).
- Keep it straightforward: one condition, one provider, minimal labs."""

    storyline_context = ""
    if storyline_hint:
        storyline_context = f"\nStoryline hint: {storyline_hint}"

    prompt = f"""You are a medical data generator. Generate a complete patient profile JSON for a synthetic clinical dataset.

## SCHEMA
Follow this schema EXACTLY:

{schema_content}

## EXAMPLE
Here is a complete example profile (demo tier, 15 visits). Your output must follow the same structure:

{example_json}

## YOUR TASK
Generate a complete patient profile for:
- id: "{patient_id}"
- name: "{name}"
- age: {age}
- sex: "{sex}"
- {mrn_instruction}
- tier: "{tier}"
- Conditions: {conditions_hint}
{storyline_context}

{tier_instructions}

## CRITICAL RULES — READ CAREFULLY
1. Output ONLY valid JSON. No markdown, no code fences, no explanation.
2. The "id" field must be exactly "{patient_id}".
3. The "tier" field must be exactly "{tier}".
4. ALL provider names used in visits MUST appear in the "providers" array.
5. ALL medication names in "medications_started" and "medications_discontinued" MUST appear in the "medications" array.
6. Visit refs must be unique (visit_01, visit_02, ...).
7. Visit dates must be in chronological order (earliest first).
8. All conditions MUST have an "icd_code" field with a valid ICD-10 code.
9. Document filenames MUST follow the pattern: {{type}}_{{lastname}}_{{yyyy}}_{{mon}}.pdf
   - lastname is lowercase: "{lastname}"
   - month is 3-letter lowercase: jan, feb, mar, apr, may, jun, jul, aug, sep, oct, nov, dec
   - Multiple same-type docs in same month: append _2, _3 (e.g., progress_note_{lastname}_2025_mar_2.pdf)
   - Valid doc types: intake_form, progress_note, lab_report, imaging_report, discharge_summary, referral_letter, consult_note
10. labs_document filenames must also follow the same pattern, typically lab_report_{{lastname}}_{{yyyy}}_{{mon}}.pdf
11. Lab entries MUST have "flag" as one of: "normal", "high", "low", "critical"
12. Condition status must be one of: "active", "resolved", "chronic"
13. Medication status must be one of: "active", "discontinued"
14. Visit type must be one of: "initial", "follow-up", "emergency", "routine", "consult"
15. sex must be "male" or "female"
16. Referral "to" field must be a provider name that exists in the providers array.
17. Medication "start_visit" must reference a valid visit ref. Medication "end_visit" should be null if active.
18. Each visit MUST have a "document" object with "type" and "filename" fields.
19. Each visit MUST have "chief_complaint" and "narrative" fields.
20. Use realistic clinical dates in 2024-2025 range.

Generate the complete JSON now:"""

    return prompt


def main():
    env = load_env()
    api_key = env.get("GEMINI_API_KEY", "")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in .env")
        sys.exit(1)

    # Load schema and example
    schema_content = SCHEMA_PATH.read_text()
    example_json = EXAMPLE_PATH.read_text()

    # Combine all patients to generate
    all_patients = STUB_PATIENTS + COMPLEX_PATIENTS + MODERATE_PATIENTS + SIMPLE_PATIENTS

    # Track used MRNs
    used_mrns = {"MRN-78234", "MRN-41092", "MRN-55671", "MRN-33890", "MRN-62417", "MRN-91447"}

    # Ensure output dir exists
    PATIENTS_DIR.mkdir(parents=True, exist_ok=True)

    succeeded = 0
    failed = 0

    for pdef in all_patients:
        patient_id = pdef["patient_id"]
        name = pdef["name"]
        tier = pdef["tier"]
        mrn = pdef.get("mrn", "")
        output_path = PATIENTS_DIR / f"{patient_id}.json"

        # Skip if already exists and is valid
        if output_path.exists():
            try:
                existing = json.loads(output_path.read_text())
                errors = validate_profile(existing, patient_id, tier)
                if not errors:
                    print(f"Skipping {patient_id} ({name}, {tier}) — already exists and valid")
                    if existing.get("mrn"):
                        used_mrns.add(existing["mrn"])
                    succeeded += 1
                    continue
                else:
                    print(f"Re-generating {patient_id} ({name}, {tier}) — existing has errors: {errors[:2]}")
            except (json.JSONDecodeError, Exception):
                print(f"Re-generating {patient_id} ({name}, {tier}) — existing file is invalid")

        print(f"Generating {patient_id} ({name}, {tier})... ", end="", flush=True)

        prompt = build_prompt(schema_content, example_json, pdef)
        profile = call_gemini(api_key, prompt)

        if profile is None:
            print("FAILED (API returned no valid response after retries)")
            failed += 1
            continue

        # Apply fixes
        profile = fix_profile(
            profile,
            patient_id,
            tier,
            expected_name=name,
            expected_mrn=mrn if mrn else None,
        )

        # Ensure MRN is unique
        if not mrn:  # Generated MRN
            while profile["mrn"] in used_mrns:
                import random
                profile["mrn"] = f"MRN-{random.randint(10000, 99999):05d}"

        used_mrns.add(profile["mrn"])

        # Validate
        errors = validate_profile(profile, patient_id, tier)
        if errors:
            print(f"WARNINGS after fix: {errors[:3]}")
            # Try one more generation
            print(f"  Retrying {patient_id}... ", end="", flush=True)
            profile2 = call_gemini(api_key, prompt)
            if profile2:
                profile2 = fix_profile(profile2, patient_id, tier, expected_name=name, expected_mrn=mrn if mrn else None)
                if not mrn:
                    while profile2["mrn"] in used_mrns:
                        import random
                        profile2["mrn"] = f"MRN-{random.randint(10000, 99999):05d}"
                errors2 = validate_profile(profile2, patient_id, tier)
                if len(errors2) < len(errors):
                    profile = profile2
                    errors = errors2
                    used_mrns.add(profile["mrn"])

        if errors:
            print(f"saving with {len(errors)} remaining issues: {errors[:2]}")
        else:
            print("done")

        # Save
        with open(output_path, "w") as f:
            json.dump(profile, f, indent=2)
            f.write("\n")

        succeeded += 1

        # Rate limit: small delay between requests
        time.sleep(1)

    print(f"\n=== Generation complete: {succeeded} succeeded, {failed} failed ===")

    # Final validation pass
    print("\n--- Final validation ---")
    all_mrns = set()
    all_names = set()
    total_errors = 0
    for path in sorted(PATIENTS_DIR.glob("patient_*.json")):
        try:
            profile = json.loads(path.read_text())
            pid = profile.get("id", path.stem)
            tier = profile.get("tier", "?")
            errors = validate_profile(profile, pid, tier)
            if errors:
                print(f"  {pid}: {len(errors)} errors — {errors[:2]}")
                total_errors += len(errors)

            mrn = profile.get("mrn", "")
            if mrn in all_mrns:
                print(f"  {pid}: DUPLICATE MRN {mrn}")
                total_errors += 1
            all_mrns.add(mrn)

            name = profile.get("name", "")
            if name in all_names:
                print(f"  {pid}: DUPLICATE NAME {name}")
                total_errors += 1
            all_names.add(name)
        except Exception as e:
            print(f"  {path.stem}: PARSE ERROR — {e}")
            total_errors += 1

    if total_errors == 0:
        print("  All profiles valid!")
    else:
        print(f"  Total issues: {total_errors}")


if __name__ == "__main__":
    main()
