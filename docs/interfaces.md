# MedGate — Interface Contracts

**Parent:** [TECHNICAL.md](../TECHNICAL.md)
**Owner:** Whole team
**Status:** PROPOSED — needs team agreement before implementation begins
**Last updated:** 2026-03-28

This document defines every data structure that crosses a workstream boundary. Once agreed, each person can build to these contracts independently.

---

## 1. REST API (Frontend → Backend)

### `POST /api/query`

Start a new clinical query. Returns an SSE stream.

**Request:**
```json
{
  "message": "Tell me about John Smith, he's been having headaches",
  "model": "claude"
}
```

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `message` | string | yes | Raw clinician query (may contain PHI) |
| `model` | string | yes | `"claude"` \| `"gpt4"` \| `"gemini"` |

**Response:** `Content-Type: text/event-stream` — see §2 for event definitions.

---

### `GET /api/graph`

Returns the full knowledge graph for the 3D visualization.

**Response:**
```json
{
  "nodes": [
    {
      "id": "patient_001",
      "type": "patient",
      "label": "John Smith",
      "color": "#4A90D9",
      "size": 12,
      "metadata": {
        "age": 31,
        "sex": "male",
        "summary": "31yo male with recurring headaches..."
      }
    },
    {
      "id": "lab_045",
      "type": "lab_result",
      "label": "ANA Panel",
      "color": "#9B59B6",
      "size": 6,
      "metadata": {
        "test_name": "ANA",
        "value": "1:320",
        "flag": "high",
        "date": "2025-10-15"
      },
      "source_pdf": "lab_report_2025_oct.pdf",
      "source_page": 2
    }
  ],
  "edges": [
    {
      "source": "patient_001",
      "target": "visit_012",
      "type": "HAD_VISIT"
    },
    {
      "source": "visit_012",
      "target": "lab_045",
      "type": "RESULTED_IN"
    }
  ]
}
```

**Node shape:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string | yes | Unique across all nodes |
| `type` | string | yes | `"patient"` \| `"visit"` \| `"condition"` \| `"medication"` \| `"lab_result"` \| `"procedure"` \| `"provider"` |
| `label` | string | yes | Display name for info card |
| `color` | string | yes | Hex color for rendering |
| `size` | number | yes | Relative node size for the graph |
| `metadata` | object | yes | Type-specific fields (see §4 for full schemas) |
| `source_pdf` | string | no | Filename of source document |
| `source_page` | number | no | Page number in source document |
| `sources` | array | no | `[{pdf, page}]` — for nodes with multiple sources |

**Edge shape:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `source` | string | yes | Source node `id` |
| `target` | string | yes | Target node `id` |
| `type` | string | yes | One of the 9 edge types (see §4) |

---

### `GET /api/pdf/:filename`

Serves a source PDF file. Query param `page` is informational (frontend handles page navigation).

**Request:** `GET /api/pdf/lab_report_2025_oct.pdf?page=2`

**Response:** `Content-Type: application/pdf` — raw PDF bytes.

---

### `GET /api/models`

Returns available cloud model options.

**Response:**
```json
{
  "models": [
    { "id": "claude",  "name": "Claude",  "available": true },
    { "id": "gpt4",    "name": "GPT-4",   "available": true },
    { "id": "gemini",  "name": "Gemini",  "available": true }
  ]
}
```

---

## 2. SSE Events (Backend → Frontend)

All events follow the standard SSE format: `event: <type>\ndata: <json>\n\n`

Events are emitted in order during a single query lifecycle:

### Event sequence

```
1. deidentified_query        (once)
2. cloud_thinking            (once, when cloud model starts)
3. gatekeeper_query          ─┐
4. graph_traversal            │ repeated 1-N times
5. gatekeeper_response       ─┘
6. cloud_response_chunk      (streamed, many)
7. final_response            (once, terminates the stream)
```

### Event definitions

#### `deidentified_query`
Emitted after the gatekeeper strips PHI. Displayed in the redacted view.

```json
{
  "type": "deidentified_query",
  "content": "[PATIENT_1], 31, male, presenting with recurring headaches and joint pain for approximately 8 months",
  "token_summary": {
    "PATIENT_1": "patient_name",
    "DATE_1": "date"
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `content` | string | The sanitized query with tokens |
| `token_summary` | object | Token → PHI category (NOT the real value). For the redacted view to show what types of PHI were stripped. |

---

#### `cloud_thinking`
Emitted when the cloud model begins processing. Shown as a status indicator in the chat.

```json
{
  "type": "cloud_thinking",
  "content": "Analyzing query and requesting clinical context..."
}
```

---

#### `gatekeeper_query`
Emitted when the cloud model calls `query_gatekeeper`. Displayed in the redacted view.

```json
{
  "type": "gatekeeper_query",
  "content": "What are the lab results for [PATIENT_1] from the past 12 months?",
  "turn": 1
}
```

| Field | Type | Notes |
|-------|------|-------|
| `content` | string | The cloud model's query (contains tokens, never real PHI) |
| `turn` | number | Which gatekeeper round this is (1, 2, 3...) |

---

#### `graph_traversal`
Emitted when the gatekeeper accesses nodes in the knowledge graph. Triggers traversal highlighting in the 3D graph.

```json
{
  "type": "graph_traversal",
  "nodes": ["patient_001", "visit_012", "lab_045", "lab_046"],
  "edges": [
    { "source": "patient_001", "target": "visit_012" },
    { "source": "visit_012", "target": "lab_045" },
    { "source": "visit_012", "target": "lab_046" }
  ],
  "turn": 1
}
```

| Field | Type | Notes |
|-------|------|-------|
| `nodes` | string[] | IDs of nodes accessed in this traversal |
| `edges` | object[] | Edges traversed (for path highlighting animation) |
| `turn` | number | Matches the `gatekeeper_query` turn |

---

#### `gatekeeper_response`
Emitted after the gatekeeper composes its redacted response. Displayed in the redacted view.

```json
{
  "type": "gatekeeper_response",
  "content": "ANA positive, titer 1:320 [REF_1]. ESR elevated at 45 mm/hr [REF_2]. CBC within normal limits [REF_3].",
  "turn": 1,
  "refs_added": ["REF_1", "REF_2", "REF_3"]
}
```

| Field | Type | Notes |
|-------|------|-------|
| `content` | string | Redacted response with `[REF_N]` tokens |
| `turn` | number | Matches the `gatekeeper_query` turn |
| `refs_added` | string[] | Which REF tokens were introduced in this response |

---

#### `cloud_response_chunk`
Streamed token-by-token as the cloud model produces its final answer (still redacted at this stage). Optional — only if the team wants to show a "typing" effect in the redacted view.

```json
{
  "type": "cloud_response_chunk",
  "content": "Based on",
  "done": false
}
```

---

#### `final_response`
The fully re-hydrated response with real names and resolved citations. This is what the clinician sees.

```json
{
  "type": "final_response",
  "content": "Based on John Smith's clinical history, the recurring headaches, joint pain, and abnormal ANA results suggest evaluation for systemic lupus erythematosus.",
  "citations": [
    {
      "ref_id": "REF_1",
      "index": 1,
      "display": "Lab Report — Oct 2025, p.2",
      "pdf": "lab_report_2025_oct.pdf",
      "page": 2
    },
    {
      "ref_id": "REF_2",
      "display": "Lab Report — Oct 2025, p.3",
      "index": 2,
      "pdf": "lab_report_2025_oct.pdf",
      "page": 3
    },
    {
      "ref_id": "REF_3",
      "index": 3,
      "display": "Lab Report — Nov 2025, p.1",
      "pdf": "lab_report_2025_nov.pdf",
      "page": 1
    }
  ],
  "model_used": "claude",
  "gatekeeper_turns": 3
}
```

| Field | Type | Notes |
|-------|------|-------|
| `content` | string | Re-hydrated text with `[1]`, `[2]` etc. inline markers replacing `[REF_N]` |
| `citations` | array | Ordered list of resolved citations |
| `citations[].ref_id` | string | Original REF token (e.g. `"REF_1"`) |
| `citations[].index` | number | Display number shown to user (`[1]`, `[2]`) |
| `citations[].display` | string | Human-readable label for the citation |
| `citations[].pdf` | string | Filename — used with `GET /api/pdf/:filename` |
| `citations[].page` | number | Page to open in the PDF viewer |
| `model_used` | string | Which cloud model produced this response |
| `gatekeeper_turns` | number | How many times the cloud model queried the gatekeeper |

---

#### `error`
Emitted if something fails during processing.

```json
{
  "type": "error",
  "content": "Cloud model API returned 429 — rate limited. Try again in a few seconds.",
  "phase": "cloud_query"
}
```

| Field | Type | Notes |
|-------|------|-------|
| `content` | string | Human-readable error message |
| `phase` | string | `"deidentification"` \| `"cloud_query"` \| `"gatekeeper"` \| `"rehydration"` |

---

## 3. Graph Query Functions (Backend ↔ Graph Module)

These are the Python functions that the graph module exports and the backend/gatekeeper calls. Person 3 implements these; Person 2 calls them.

```python
# graph.py — public API

def load_graph(path: str) -> Graph:
    """Load graph.json into memory. Called once at startup."""

def get_patient(graph: Graph, *, name: str = None, id: str = None) -> Patient | None:
    """Find a patient by real name or internal ID."""

def get_patient_visits(graph: Graph, patient_id: str) -> list[Visit]:
    """All visits for a patient, sorted by date descending."""

def get_visit_labs(graph: Graph, visit_id: str) -> list[LabResult]:
    """Lab results from a specific visit."""

def get_patient_labs(graph: Graph, patient_id: str) -> list[LabResult]:
    """All lab results across all visits for a patient, sorted by date descending."""

def get_patient_medications(graph: Graph, patient_id: str) -> list[Medication]:
    """All medications for a patient (active and discontinued)."""

def get_patient_conditions(graph: Graph, patient_id: str) -> list[Condition]:
    """All conditions for a patient."""

def get_patient_procedures(graph: Graph, patient_id: str) -> list[Procedure]:
    """All procedures for a patient."""

def get_patient_providers(graph: Graph, patient_id: str) -> list[Provider]:
    """All providers who have attended this patient."""

def get_family_history(graph: Graph, patient_id: str) -> list[dict]:
    """Family medical history entries for a patient.
    Returns: [{"relation": "mother", "condition": "SLE", "source_pdf": "...", "source_page": N}]
    """

def get_node_by_id(graph: Graph, node_id: str) -> Node | None:
    """Generic node lookup by ID."""

def search_nodes(graph: Graph, query: str, node_type: str = None) -> list[Node]:
    """Simple text search across node labels and metadata.
    Used when the gatekeeper needs to find relevant nodes for a free-form question.
    """

def get_traversal_path(graph: Graph, node_ids: list[str]) -> TraversalPath:
    """Given a list of accessed node IDs, return the nodes and connecting edges.
    Used to emit graph_traversal events to the frontend.
    """
```

**Return types** are dataclasses or TypedDicts matching the node schemas in §4. The graph module returns the full node data (including PHI fields) — the backend/gatekeeper is responsible for redacting before sending anything externally.

---

## 4. Knowledge Graph JSON Schema (`graph.json`)

This is the format of `data/graph.json` — produced by Person 3, consumed by the backend at startup and served to the frontend via `GET /api/graph`.

```json
{
  "meta": {
    "generated_at": "2026-03-28T14:30:00Z",
    "num_patients": 35,
    "num_nodes": 1847,
    "num_edges": 4203
  },
  "nodes": {
    "patient_001": {
      "id": "patient_001",
      "type": "patient",
      "label": "John Smith",
      "fields": {
        "name": { "value": "John Smith", "phi": true },
        "age": { "value": 31, "phi": false },
        "sex": { "value": "male", "phi": false },
        "mrn": { "value": "MRN-78234", "phi": true },
        "summary": { "value": "31yo male with recurring headaches and joint pain over 8 months, ultimately diagnosed with SLE", "phi": false }
      },
      "source_pdf": "intake_form_smith.pdf",
      "source_page": 1
    },
    "visit_012": {
      "id": "visit_012",
      "type": "visit",
      "label": "Follow-up — Oct 2025",
      "fields": {
        "date": { "value": "2025-10-15", "phi": true },
        "visit_type": { "value": "follow-up", "phi": false },
        "chief_complaint": { "value": "persistent headaches, new joint pain", "phi": false },
        "attending_provider": { "value": "Dr. Sarah Chen", "phi": true },
        "notes": { "value": "Patient reports worsening bilateral joint pain...", "phi": false }
      },
      "source_pdf": "progress_note_smith_oct2025.pdf",
      "source_page": 1
    },
    "lab_045": {
      "id": "lab_045",
      "type": "lab_result",
      "label": "ANA Panel",
      "fields": {
        "test_name": { "value": "ANA", "phi": false },
        "value": { "value": "1:320", "phi": false },
        "unit": { "value": "titer", "phi": false },
        "reference_range": { "value": "<1:40", "phi": false },
        "flag": { "value": "high", "phi": false },
        "date": { "value": "2025-10-15", "phi": true }
      },
      "source_pdf": "lab_report_smith_oct2025.pdf",
      "source_page": 2
    }
  },
  "edges": [
    { "source": "patient_001", "target": "visit_012", "type": "HAD_VISIT" },
    { "source": "visit_012", "target": "lab_045", "type": "RESULTED_IN" },
    { "source": "patient_001", "target": "condition_008", "type": "HAS_CONDITION" }
  ]
}
```

### PHI tagging convention

Every field is wrapped as `{ "value": <actual_value>, "phi": <bool> }`. This lets the gatekeeper code generically redact any field where `phi: true` without hardcoding field names. The frontend's `GET /api/graph` response strips the wrapper — the backend serves `metadata` as flat key-value pairs (see §1 `GET /api/graph`).

### Node type visual config

Hardcoded in the frontend, but agreed here for consistency:

| Type | Color | Size | Notes |
|------|-------|------|-------|
| `patient` | `#4A90D9` (blue) | 12 | Largest — anchor nodes |
| `visit` | `#F5C542` (yellow) | 8 | |
| `condition` | `#E74C3C` (red) | 8 | |
| `medication` | `#2ECC71` (green) | 8 | |
| `lab_result` | `#9B59B6` (purple) | 6 | Smallest — most numerous |
| `procedure` | `#E67E22` (orange) | 8 | |
| `provider` | `#1ABC9C` (teal) | 8 | |

### Edge types (exhaustive list)

| Edge | Source → Target | Notes |
|------|-----------------|-------|
| `HAS_CONDITION` | patient → condition | |
| `PRESCRIBED` | patient → medication | |
| `HAD_VISIT` | patient → visit | |
| `RESULTED_IN` | visit → lab_result | |
| `PERFORMED` | visit → procedure | |
| `ATTENDED_BY` | visit → provider | |
| `TREATED_WITH` | condition → medication | |
| `MONITORED_BY` | medication → lab_result | |
| `REFERRED_TO` | provider → provider | |

---

## 5. Token Format Reference

For completeness — used by backend internally, visible in the redacted view:

| Token pattern | Example | PHI category |
|---------------|---------|--------------|
| `[PATIENT_N]` | `[PATIENT_1]` | Patient name |
| `[PROVIDER_N]` | `[PROVIDER_1]` | Doctor/nurse/staff name |
| `[FAMILY_N]` | `[FAMILY_1]` | Family member name |
| `[MRN_N]` | `[MRN_1]` | Medical record number |
| `[DATE_N]` | `[DATE_1]` | Replaced with relative description |
| `[LOCATION_N]` | `[LOCATION_1]` | Address, institution name |
| `[CONTACT_N]` | `[CONTACT_1]` | Phone, email |
| `[REF_N]` | `[REF_1]` | Source citation (opaque, not PHI) |

---

## 6. Dev Environment & Conventions

### 6.1 Who works where

| Person | Works on | Where | Notes |
|--------|----------|-------|-------|
| Person 1 (frontend) | `frontend/` | Local laptop | `npm run dev` on `:3000`, proxies `/api/*` to GX10 |
| Person 2 (backend) | `backend/` | GX10 via SSH | FastAPI on `:8000` bound to `0.0.0.0` |
| Person 3 (data) | `scripts/`, `data/` | Local laptop | Calls Claude/GPT-4 APIs to generate docs, SCPs `data/` to GX10 when ready |

### 6.2 Repo structure

```
backend/          ← Person 2
frontend/         ← Person 1
data/             ← Person 3
  graph.json        (production graph)
  pdfs/             (generated PDFs)
  stub/             (stub data for frontend dev — see §7)
scripts/          ← Person 3
  generate_patients.py
  generate_documents.py
  build_graph.py
docs/             ← shared
```

### 6.3 Port numbers

| Service | Port | Host | Notes |
|---------|------|------|-------|
| Frontend dev server | `:3000` | Each dev's laptop | Vite/CRA dev server |
| Backend (FastAPI) | `:8000` | GX10 | Serves API + static frontend in production |
| Ollama | `:11434` | GX10 | Already running as systemd service |

Frontend proxies `/api/*` → `http://GX10_HOST:8000/api/*` in dev mode. On demo day, the backend serves the built frontend static files directly — no separate frontend server.

### 6.4 PDF naming convention

Pattern: `{type}_{lastname}_{yyyy}_{mon}.pdf`

| Document type | Prefix |
|---------------|--------|
| Lab report | `lab_report` |
| Discharge summary | `discharge_summary` |
| Progress note | `progress_note` |
| Imaging report | `imaging_report` |
| Referral letter | `referral_letter` |
| Intake form | `intake_form` |

Examples:
```
lab_report_smith_2025_oct.pdf
discharge_summary_smith_2025_nov.pdf
progress_note_garcia_2026_jan.pdf
```

Multiple docs of the same type in the same month: append `_2`, `_3`, etc.:
```
progress_note_smith_2025_oct.pdf
progress_note_smith_2025_oct_2.pdf
```

---

## 7. Stub Data

Stub data lives in `data/stub/` and `backend/stub_server.py`. These exist so Person 1 (frontend) can build the full UI without waiting for the real backend or graph data.

- **`data/stub/graph.json`** — 5 patients, ~30 nodes, realistic edges. Use with `GET /api/graph`.
- **`backend/stub_server.py`** — A standalone FastAPI server that serves the stub graph and emits hardcoded SSE events for a fake query. Responds to all endpoints defined in §1.

Delete or ignore these once the real backend and data are ready.

---

*This document is the interface contract for the MedGate hackathon. All three workstreams build to these definitions. If a change is needed, discuss with the team and update this doc before implementing. Last updated: 2026-03-28.*
