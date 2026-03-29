# Patient Profile Schema

## Purpose

Patient profiles are the **single source of truth** for both `scripts/generate_documents.py` (produces PDFs) and `scripts/build_graph.py` (produces graph.json). The graph is built directly from profiles, NOT extracted from generated PDFs. PDFs are visual artifacts; profiles are the structured data.

## File Convention

- One file per patient: `data/patients/{patient_id}.json` (e.g., `patient_001.json`)
- Patient IDs: `patient_NNN` format (zero-padded to 3 digits)

## Top-Level Fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string | yes | Format: `patient_NNN` |
| `name` | string | yes | Full name (PHI) |
| `age` | number | yes | |
| `sex` | string | yes | `"male"` or `"female"` |
| `mrn` | string | yes | Format: `MRN-NNNNN` |
| `dob` | string | yes | ISO date `YYYY-MM-DD`, date of birth |
| `summary` | string | yes | 1-2 sentence clinical overview |
| `tier` | string | yes | `"demo"` \| `"complex"` \| `"moderate"` \| `"simple"` |
| `storyline` | string | required for demo/complex | Narrative arc of the clinical case |
| `conditions` | array | yes | See Conditions below |
| `medications` | array | yes | See Medications below |
| `family_history` | array | no | See Family History below |
| `providers` | array | yes | See Providers below |
| `visits` | array | yes | See Visits below |

## Conditions Array

Each entry:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | yes | Display name (e.g., "Systemic Lupus Erythematosus") |
| `icd_code` | string | yes | ICD-10 code (e.g., "M32.9") |
| `status` | string | yes | `"active"` \| `"resolved"` \| `"chronic"` |
| `diagnosed_visit` | string | no | Ref to a visit (e.g., `"visit_07"`) |
| `notes` | string | no | Additional clinical context |
| `discoverable` | boolean | no | Default `false`. When `true`, `build_graph.py` skips the `HAS_CONDITION` edge — the condition node is still created but not connected to the patient. Used for demo patients where the cloud model should discover the diagnosis via reasoning. |

## Medications Array

Each entry:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | yes | Medication name (e.g., "Hydroxychloroquine") |
| `dosage` | string | yes | (e.g., "200mg") |
| `frequency` | string | yes | (e.g., "twice daily") |
| `start_visit` | string | yes | Ref to visit where prescribed |
| `end_visit` | string | no | Ref to visit where discontinued (null if active) |
| `status` | string | yes | `"active"` \| `"discontinued"` |
| `treats` | string | no | Condition name this treats (creates TREATED_WITH edge) |
| `monitored_by_labs` | array | no | Lab test names that monitor this med (creates MONITORED_BY edges) |
| `notes` | string | no | Additional context |

## Family History Array

Each entry:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `relation` | string | yes | e.g., "mother", "maternal aunt", "father" |
| `condition` | string | yes | Medical condition name |
| `diagnosed_age` | number | no | Age at which relative was diagnosed |

## Providers Array

Each entry:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | yes | Full name with title (e.g., "Dr. Sarah Chen") |
| `role` | string | yes | e.g., "attending", "specialist" |
| `department` | string | yes | e.g., "Internal Medicine", "Rheumatology" |

## Visits Array

Ordered chronologically. Each entry:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `ref` | string | yes | Unique reference (e.g., `"visit_01"`). Used by cross-references. |
| `date` | string | yes | ISO format `YYYY-MM-DD` |
| `type` | string | yes | `"initial"` \| `"follow-up"` \| `"emergency"` \| `"routine"` \| `"consult"` |
| `provider` | string | yes | Provider name (must exist in providers array) |
| `chief_complaint` | string | yes | Reason for visit |
| `narrative` | string | yes | 1-3 paragraph clinical narrative |
| `document` | object | yes | See Document below |
| `labs` | array | no | See Labs below |
| `labs_document` | object | no | Separate PDF for lab results |
| `procedures` | array | no | See Procedures below |
| `medications_started` | array | no | Medication names started at this visit (must exist in medications array) |
| `medications_discontinued` | array | no | Medication names discontinued at this visit |
| `referrals` | array | no | See Referrals below |

### Document Object

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `type` | string | yes | One of: `intake_form`, `progress_note`, `lab_report`, `imaging_report`, `discharge_summary`, `referral_letter`, `consult_note`, `cdc_advisory` |
| `filename` | string | yes | Convention: `{type}_{lastname}_{yyyy}_{mon}.pdf`. Multiple same-type docs in same month: append `_2`, `_3`, etc. |

### Labs Array Entry

| Field | Type | Required |
|-------|------|----------|
| `test` | string | yes |
| `value` | string | yes |
| `unit` | string | yes |
| `range` | string | yes |
| `flag` | string | yes — `"normal"` \| `"high"` \| `"low"` \| `"critical"` |

### Procedures Array Entry

| Field | Type | Required |
|-------|------|----------|
| `name` | string | yes |
| `outcome` | string | yes |

### Referrals Array Entry

| Field | Type | Required |
|-------|------|----------|
| `to` | string | yes — provider name (must exist in providers array) |
| `reason` | string | yes |

## Tier Requirements

| Tier | Visits | Storyline | Notes |
|------|--------|-----------|-------|
| `demo` | >= 15 | required | Showcase patients for live demo |
| `complex` | >= 15 | required | Rich clinical histories |
| `moderate` | 5-10 | optional | A few conditions, some visits |
| `simple` | 2-3 | optional | Single visit, straightforward |

## Graph Mapping

How `build_graph.py` converts profile sections to graph nodes and edges:

| Profile section | Node type | Edge type |
|----------------|-----------|-----------|
| Top-level patient fields | `patient` | — |
| `visits[]` | `visit` | `HAD_VISIT` (patient → visit) |
| `conditions[]` | `condition` | `HAS_CONDITION` (patient → condition) — edge created only when `discoverable` is `false` (default) |
| `medications[]` | `medication` | `PRESCRIBED` (patient → medication) |
| `visits[].labs[]` | `lab_result` | `RESULTED_IN` (visit → lab_result) |
| `visits[].procedures[]` | `procedure` | `PERFORMED` (visit → procedure) |
| `providers[]` | `provider` (deduplicated) | `ATTENDED_BY` (visit → provider) |
| `family_history[]` | `family_history` | `HAS_FAMILY_HISTORY` (patient → family_history) |
| `medications[].treats` | — | `TREATED_WITH` (condition → medication) |
| `medications[].monitored_by_labs` | — | `MONITORED_BY` (medication → lab_result) |
| `visits[].referrals[]` | — | `REFERRED_TO` (provider → provider) |

## PDF Filename Convention

Pattern: `{type}_{lastname}_{yyyy}_{mon}.pdf`

- Lastname is lowercase
- Month is 3-letter lowercase abbreviation (jan, feb, mar, apr, may, jun, jul, aug, sep, oct, nov, dec)
- Multiple docs of same type in same month: append `_2`, `_3`
- Examples: `progress_note_smith_2025_oct.pdf`, `lab_report_reed_2025_aug_2.pdf`

## Validation Rules

1. All provider names in visits must exist in the providers array
2. All medication names in medications_started/discontinued must exist in the medications array
3. Visit refs must be unique within a profile
4. Visit dates must be chronological
5. Document filenames must follow the naming convention
6. No two profiles may share an MRN or name
7. All conditions must have an icd_code
8. Demo/complex tier profiles must have a storyline and >= 15 visits
