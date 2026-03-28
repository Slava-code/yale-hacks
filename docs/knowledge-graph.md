# MedGate — Knowledge Graph & Data Generation Spec

**Extracted from:** `TECHNICAL.md` sections 2, 10
**Owner:** Data/pipeline developer
**Last updated:** 2026-03-28

This document covers the knowledge graph schema, storage format, PHI tagging, and the synthetic data generation pipeline. For the full technical context, see `TECHNICAL.md`. For product requirements, see `PRD.md`.

---

## 1. Storage Format

For the hackathon, the knowledge graph is stored as **JSON** — a single file (or a small set of files) loaded into memory at startup. No database needed. The GX10 has 128GB of unified memory; a graph of 1,000–2,000 nodes with several thousand edges will occupy a trivially small amount of memory, likely under 50MB even with generous metadata per node.

**Decision rationale:** SQLite, Neo4j, and other graph databases were considered but add unnecessary complexity for the hackathon. JSON is human-readable, easy to debug, easy to generate, and fast to load. If the graph were millions of nodes, we'd need a database. At ~2,000 nodes, in-memory JSON is fine.

The graph file is loaded once at server startup and held in memory for the duration of the session. The gatekeeper queries it by traversing the in-memory structure — no disk I/O during queries.

---

## 2. Schema

The graph consists of **nodes** and **edges**.

### Node types and their fields

```
PATIENT
  - id: string (internal, e.g., "patient_001")
  - name: string (real name — PHI, never leaves GX10)
  - age: number
  - sex: string
  - mrn: string (PHI)
  - summary: string (brief clinical overview)

VISIT
  - id: string
  - patient_id: string (FK)
  - date: string (real date — PHI; converted to relative at query time)
  - type: string (e.g., "emergency", "follow-up", "routine")
  - chief_complaint: string
  - attending_provider: string (PHI — provider name)
  - notes: string (clinical narrative)
  - source_pdf: string (file path to source document)
  - source_page: number

CONDITION
  - id: string
  - name: string (e.g., "Type 2 Diabetes", "Hypertension")
  - icd_code: string (optional)
  - status: string ("active", "resolved", "chronic")
  - diagnosed_date: string (relative)

MEDICATION
  - id: string
  - name: string (e.g., "Metformin 500mg")
  - dosage: string
  - frequency: string
  - prescribing_provider: string (PHI)
  - start_date: string
  - status: string ("active", "discontinued")

LAB_RESULT
  - id: string
  - test_name: string (e.g., "CBC", "ANA", "ESR")
  - value: string
  - unit: string
  - reference_range: string
  - flag: string ("normal", "high", "low", "critical")
  - date: string
  - source_pdf: string
  - source_page: number

PROCEDURE
  - id: string
  - name: string
  - date: string
  - provider: string (PHI)
  - outcome: string

PROVIDER
  - id: string
  - name: string (PHI)
  - role: string (e.g., "attending", "specialist", "nurse")
  - department: string
```

### Edge types

```
PATIENT → HAS_CONDITION → CONDITION
PATIENT → PRESCRIBED → MEDICATION
PATIENT → HAD_VISIT → VISIT
VISIT → RESULTED_IN → LAB_RESULT
VISIT → PERFORMED → PROCEDURE
VISIT → ATTENDED_BY → PROVIDER
CONDITION → TREATED_WITH → MEDICATION
MEDICATION → MONITORED_BY → LAB_RESULT
PROVIDER → REFERRED_TO → PROVIDER
```

### Source provenance

Every node that was extracted from a document stores `source_pdf` (file path) and `source_page` (page number). Nodes that aggregate information across multiple documents (e.g., a CONDITION node built from mentions across 5 visits) store an array of sources: `sources: [{pdf: "...", page: N}, ...]`. The first source is treated as the primary citation.

---

## 3. PHI Tagging

Each node field is tagged as either `phi` or `safe` in the schema definition. The gatekeeper uses these tags to determine what to tokenize when composing a response:

- `phi` fields: `name` (patient, provider), `mrn`, `ssn`, `address`, `phone`, `email`, `date` (exact), `source_pdf` (file path contains institution info)
- `safe` fields: `age`, `sex`, `condition name`, `medication name`, `lab values`, `symptoms`, `dosage`, all clinical data

This tagging is baked into the graph at construction time so the gatekeeper doesn't need to make real-time NER decisions — it just checks the tag.

---

## 4. Mock Data Generation

### 4.1 Strategy

Use Claude or GPT-4 to batch-generate synthetic clinical documents. The pipeline:

1. **Design patient profiles** — Create 30–40 fictional patients with varying complexity. Each profile defines: name, age, sex, conditions, medication history, visit history outline, family history, and primary storyline (e.g., "chronic fatigue leading to lupus diagnosis over 12 months").

2. **Generate documents per patient** — For each patient, generate the specific clinical documents their profile calls for. A complex patient might need: initial intake form, 4 progress notes, 3 lab reports, 1 imaging report, 1 specialist referral, 1 discharge summary = 11 documents. A simple patient might need 2–3.

3. **Convert to PDF** — Use a PDF generation library (reportlab, WeasyPrint, or Markdown → PDF via pandoc) to convert the generated text into realistic-looking clinical PDFs with headers, dates, patient info blocks, etc.

4. **Extract to knowledge graph** — Run NER/extraction (can use Claude or GPT-4 for this offline step) over each document to produce structured node/edge JSON. This step also records source_pdf and source_page per extracted fact.

5. **Validate** — Manually review a sample of generated documents and graph nodes to ensure consistency (same patient referenced across documents has consistent details).

### 4.2 Patient Distribution

Target: ~300 documents across 30–40 patients.

- **5–8 complex patients** (15–25 docs each): chronic conditions, multi-year histories, multiple specialists, changing medications. These are the demo showcase patients.
- **10–15 moderate patients** (5–10 docs each): a few visits, a condition or two, some labs.
- **15–20 simple patients** (2–3 docs each): single visit, straightforward presentation.

This distribution creates a realistic-looking graph where some patient clusters are dense and others are sparse.

### 4.3 Demo Showcase Patient

At least one patient should be specifically designed for the demo scenario — a complex case where symptoms accrue over multiple visits and converge on a specific diagnosis. The demo patient should:
- Have 15+ documents spanning 8–12 months
- Present with individually mild symptoms that together suggest a specific condition
- Have lab results that are diagnostically significant but not immediately obvious
- Have family history that supports the diagnosis
- Result in a differential diagnosis that frontier models reliably identify

Test this patient's documents against Claude, GPT-4, and Gemini 20+ times to confirm all three models produce interesting, multi-turn reasoning before committing to it as the demo case.

---

## 5. File Structure (Data & Scripts)

```
data/
├── graph.json                  # Pre-built knowledge graph
├── pdfs/                       # Source PDF documents (~300 files)
└── patients/                   # Patient profile definitions (used for generation)

scripts/
├── generate_patients.py        # Generate patient profiles
├── generate_documents.py       # Generate synthetic clinical docs
├── build_graph.py              # Extract entities and build graph.json
└── test_demo_scenario.py       # Automated testing of demo case across models
```
