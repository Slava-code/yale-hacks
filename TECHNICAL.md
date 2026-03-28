# MedGate — Technical Implementation Document

**Date:** 2026-03-28
**Status:** Draft
**Companion to:** `PRODUCT_DESCRIPTION.md` (source of truth for product requirements)

This document captures the technical decisions made during architecture planning. It is intended for all team members and coding agents as the implementation reference. Where this document is silent, defer to the PRD. Where this document specifies a technical approach, it takes precedence over any assumptions.

---

## 1. System Architecture Overview

MedGate is a three-component system: a **custom frontend** (browser-based), a **GX10 backend** (local server running the gatekeeper model + knowledge graph), and **cloud AI APIs** (Claude, GPT-4, Gemini). The GX10 backend is the central hub — it sits between the frontend and the cloud and mediates all communication.

```
┌──────────┐       ┌──────────────────────────────┐       ┌──────────────┐
│ Frontend │──────▶│        GX10 Backend           │──────▶│  Cloud AI    │
│ (Browser)│◀──────│                                │◀──────│  (Claude /   │
└──────────┘       │  ┌─────────────────────────┐  │       │   GPT-4 /    │
                   │  │  Gatekeeper Model (GPU) │  │       │   Gemini)    │
                   │  └─────────────────────────┘  │       └──────────────┘
                   │  ┌─────────────────────────┐  │
                   │  │  Knowledge Graph (RAM)   │  │
                   │  └─────────────────────────┘  │
                   │  ┌─────────────────────────┐  │
                   │  │  Source PDFs (SSD)       │  │
                   │  └─────────────────────────┘  │
                   │  ┌─────────────────────────┐  │
                   │  │  Ephemeral Token Map     │  │
                   │  │  (RAM, per-session)      │  │
                   │  └─────────────────────────┘  │
                   └──────────────────────────────┘
```

**Critical design constraint:** The frontend NEVER communicates directly with cloud AI APIs. All traffic flows through the GX10 backend. This is what makes the privacy architecture enforceable — the frontend is just a UI, the GX10 is the control plane.

---

## 2. Knowledge Graph

### 2.1 Storage Format

For the hackathon, the knowledge graph is stored as **JSON** — a single file (or a small set of files) loaded into memory at startup. No database needed. The GX10 has 128GB of unified memory; a graph of 1,000–2,000 nodes with several thousand edges will occupy a trivially small amount of memory, likely under 50MB even with generous metadata per node.

**Decision rationale:** SQLite, Neo4j, and other graph databases were considered but add unnecessary complexity for the hackathon. JSON is human-readable, easy to debug, easy to generate, and fast to load. If the graph were millions of nodes, we'd need a database. At ~2,000 nodes, in-memory JSON is fine.

The graph file is loaded once at server startup and held in memory for the duration of the session. The gatekeeper queries it by traversing the in-memory structure — no disk I/O during queries.

### 2.2 Schema

The graph consists of **nodes** and **edges**.

**Node types and their fields:**

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

**Edge types:**

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

**Source provenance:** Every node that was extracted from a document stores `source_pdf` (file path) and `source_page` (page number). Nodes that aggregate information across multiple documents (e.g., a CONDITION node built from mentions across 5 visits) store an array of sources: `sources: [{pdf: "...", page: N}, ...]`. The first source is treated as the primary citation.

### 2.3 PHI Tagging

Each node field is tagged as either `phi` or `safe` in the schema definition. The gatekeeper uses these tags to determine what to tokenize when composing a response:

- `phi` fields: `name` (patient, provider), `mrn`, `ssn`, `address`, `phone`, `email`, `date` (exact), `source_pdf` (file path contains institution info)
- `safe` fields: `age`, `sex`, `condition name`, `medication name`, `lab values`, `symptoms`, `dosage`, all clinical data

This tagging is baked into the graph at construction time so the gatekeeper doesn't need to make real-time NER decisions — it just checks the tag.

---

## 3. Gatekeeper Model

### 3.1 Hardware Context

The ASUS Ascent GX10 is powered by the **NVIDIA GB10 Grace Blackwell Superchip** — a fused CPU+GPU package, not a low-power NPU:

- **GPU:** NVIDIA Blackwell — 6,144 CUDA cores, 5th-gen Tensor Cores
- **CPU:** 20-core ARM v9.2-A Grace CPU (10x Cortex-X925 + 10x Cortex-A725)
- **AI compute:** Up to **1 petaFLOP (1,000 TOPS)** at FP4 precision
- **Memory:** 128GB unified LPDDR5x at 273 GB/s (shared between CPU and GPU, like Apple Silicon)
- **Interconnect:** NVLink C2C at 600 GB/s bidirectional between CPU and GPU

This means nearly all 128GB is available for model loading. The memory bandwidth (273 GB/s) is the primary bottleneck for LLM inference — it determines tokens/sec for autoregressive decoding.

### 3.2 Model Selection

The gatekeeper runs locally on the GX10's Blackwell GPU. For the hackathon, the recommended model is in the **13B–27B parameter range**, using quantization formats that leverage the Blackwell Tensor Cores (FP8, MXFP4, or GGUF Q4_K_M/Q5_K_M).

**Observed inference speeds on the GX10:**

| Model Size | Tokens/sec (decode) | Time-to-first-token | Verdict |
|---|---|---|---|
| 7-8B Q4 | ~46 tok/s | <5s | Too fast to matter — model quality is the bottleneck |
| 20-27B MXFP4/Q4 | ~30-50 tok/s | ~10-15s | **Sweet spot** — fast enough for demo, much better PHI detection |
| 70B Q4/FP8 | ~3-5 tok/s | 130-180s | Too slow — TTFT kills demo flow |

**Primary candidates (test all three, pick the best for PHI identification accuracy):**

- **Qwen 2.5 32B Instruct** — excellent instruction following, strong structured output, good at entity recognition tasks. Available in GGUF Q4_K_M (~20GB). Top pick for the gatekeeper role.
- **Gemma 2 27B Instruct** — strong reasoning for its size, good at following complex system prompts. Well-tested on GB10 hardware.
- **Mistral Small 24B Instruct (v2501)** — purpose-built for structured tasks and tool use, which aligns well with the gatekeeper's role. Fast inference.

**Fallback candidates (if the above are too slow or underperform):**

- **Llama 3.1 8B Instruct** — proven baseline, ~46 tok/s, use if larger models have TTFT issues during demo
- **Phi-4 14B** — small but punches above its weight on structured tasks, good middle ground
- **Qwen 2.5 14B Instruct** — solid balance of speed and quality

**Testing protocol:** Run each candidate through 50+ de-identification tests with synthetic clinical text containing all 18 HIPAA identifier types. Track: (1) PHI detection recall (did it catch everything?), (2) false positives (did it redact clinical terms?), (3) format compliance (did it produce valid tokens?), (4) inference speed on the GX10. PHI detection recall is the most important metric — a single leaked name in the demo is catastrophic.

The gatekeeper does NOT need to be a clinical expert. Its job is to: (1) parse user queries and identify PHI fields, (2) look up information in the knowledge graph, (3) compose redacted responses with citation tokens. This is primarily a structured task, not open-ended reasoning — but the 13B-27B range gives significantly better reliability on PHI identification compared to 7B models, which is the highest-stakes part of the pipeline.

The heavy clinical reasoning happens on the cloud model (Claude, GPT-4, Gemini), which is a frontier-class model. The gatekeeper is a router/filter, not a thinker.

### 3.3 Inference Setup

The gatekeeper model runs via a local inference server on the GX10. Options:
- **Ollama** — simplest setup, good for hackathon, supports quantized models, CUDA-accelerated on GB10
- **llama.cpp server** — more control, supports NVIDIA-specific quantization formats (MXFP4), slightly better performance
- **vLLM** — best throughput, native Blackwell support, but heavier setup

**Hackathon recommendation:** Ollama for simplicity. It can be set up in minutes, supports all candidate models, runs natively on the Blackwell GPU via CUDA, and exposes a simple HTTP API that the GX10 backend can call. If we need MXFP4 quantization for better speed, switch to llama.cpp server.

The gatekeeper runs as a persistent process. It does NOT cold-start per query — the model is loaded once and stays in memory. At the 27B Q4 level, the model occupies ~18-20GB of the 128GB unified memory, leaving >100GB for the knowledge graph, token mappings, and OS.

### 3.4 Gatekeeper System Prompt

The gatekeeper is instructed via system prompt. This prompt defines its role, its access to the knowledge graph, and its response format. Draft:

```
You are the MedGate Gatekeeper — a privacy-preserving clinical data librarian 
running on a secure on-premises device. You mediate between clinicians and 
external AI models.

You have access to a clinical knowledge graph containing patient records, 
conditions, medications, lab results, visits, and procedures. You will receive 
two types of requests:

TYPE 1 — USER QUERY DE-IDENTIFICATION:
When you receive a raw clinician query, you must:
1. Identify all Protected Health Information (PHI): patient names, provider 
   names, MRNs, SSNs, dates (convert to relative), addresses, phone numbers, 
   emails, and any other HIPAA identifiers.
2. Replace each PHI element with a token: [PATIENT_1], [PROVIDER_1], [DATE_1], etc.
3. Preserve all clinical information: age (except 90+), sex, conditions, 
   symptoms, medications, lab values, procedures.
4. Return the de-identified query.
5. Internally store the mapping (token → real value) for later re-hydration.

TYPE 2 — KNOWLEDGE RETRIEVAL:
When you receive a query from the external AI model asking for clinical context 
(e.g., "What are [PATIENT_1]'s lab results?"), you must:
1. Resolve [PATIENT_1] using your internal mapping to identify the real patient.
2. Traverse the knowledge graph to find the requested information.
3. Compose a response using ONLY the information found in the graph.
4. Redact all PHI in your response using the same token mapping.
5. Append a unique opaque reference token [REF_N] after each distinct fact, 
   where N increments per fact. Internally map each [REF_N] to the source 
   document path and page number. Do NOT reveal document names, page numbers, 
   or any corpus structure to the external model.
6. Return the redacted, cited response.

RESPONSE FORMAT for knowledge retrieval:
"[PATIENT_1], 31, male. Presenting with recurring vertigo [REF_1] and tinnitus 
[REF_1], first documented approximately 8 months ago [REF_2]. Prescribed 
meclizine [REF_3]. Most recent audiometry shows unilateral hearing loss [REF_4]."

RULES:
- NEVER include real patient names, provider names, MRNs, dates, or any PHI in 
  responses that will be sent to the external model.
- NEVER reveal document names, file paths, or page numbers to the external model.
- ALWAYS use the token mapping consistently — same patient = same token across 
  the entire interaction.
- If the requested information is not in the knowledge graph, say so. Do not 
  fabricate clinical data.
```

**Note:** This is a starting prompt. It will need iteration during testing. The specific formatting instructions (how tokens are structured, where REF tokens go) should be tuned based on how well the chosen model follows them. The 13B-27B range models are significantly better at following complex system prompts than 7B models, so fewer iterations should be needed.

### 3.5 Gatekeeper Functions

The GX10 backend exposes the gatekeeper's capabilities as discrete functions rather than relying entirely on the LLM for logic. The gatekeeper model is the *interface* layer, but the actual graph traversal and token management are handled by deterministic code:

```
deidentify_query(raw_query) → {sanitized_query, token_mapping}
  - Model identifies PHI spans in the raw query
  - Code generates random tokens and builds the mapping dict
  - Code performs the string replacement
  - Returns sanitized query + mapping

query_knowledge_graph(question, token_mapping) → redacted_response
  - Model parses the question to determine what's being asked
  - Code traverses the graph to find matching nodes
  - Code composes the raw response with real values
  - Model/code redacts PHI using the existing token mapping
  - Code assigns [REF_N] tokens and maps them to source_pdf + source_page
  - Returns the redacted, cited response

rehydrate_response(cloud_response, token_mapping, ref_mapping) → final_response
  - Code replaces all [PATIENT_N], [PROVIDER_N], etc. with real values
  - Code replaces all [REF_N] with clickable citation objects
  - Returns the final response with real names and clickable links
```

**Key principle:** Use the LLM for understanding natural language (parsing queries, identifying PHI spans). Use deterministic code for token generation, graph traversal, string replacement, and re-hydration. This keeps the privacy-critical operations reliable and auditable rather than relying on LLM output consistency.

---

## 4. Token Mapping System

### 4.1 Token Format

Tokens follow the pattern `[TYPE_N]` where TYPE indicates the category and N is an incrementing integer per category:

```
[PATIENT_1], [PATIENT_2]      — patient names
[PROVIDER_1], [PROVIDER_2]    — doctor/nurse/staff names
[FAMILY_1]                    — family member names
[MRN_1]                       — medical record numbers
[DATE_1], [DATE_2]            — specific dates (replaced with relative descriptions)
[LOCATION_1]                  — addresses, institutions
[CONTACT_1]                   — phone numbers, emails
[REF_1], [REF_2], [REF_3]    — source document citations (opaque)
```

### 4.2 Mapping Lifecycle

```
1. User submits query
2. Gatekeeper parses query, identifies PHI spans
3. Token mapping created: { "[PATIENT_1]": "John Smith", "[MRN_1]": "MRN-12345", ... }
4. Reference mapping created empty: {}
5. Sanitized query sent to cloud model
6. Cloud model queries gatekeeper (0-N times)
   - Each gatekeeper response adds to the ref mapping: { "[REF_1]": {pdf: "...", page: 3}, ... }
7. Cloud model returns final response
8. Re-hydration: code replaces all tokens using both mappings
9. BOTH mappings destroyed (deleted from memory)
10. Next user query starts fresh with new mappings
```

**Critical:** Mappings are per-interaction, not per-session. Each new user query creates entirely new tokens. `[PATIENT_1]` in query #1 might map to "John Smith" and `[PATIENT_1]` in query #2 might map to "Maria Garcia." There is no persistence between interactions.

### 4.3 Token Generation

Tokens are generated by deterministic code, NOT by the LLM. The code:
1. Receives PHI spans identified by the gatekeeper model (e.g., "John Smith" at position 14-24)
2. Assigns the next available token of the appropriate type
3. Stores the mapping in a Python dict (or JS object)
4. Performs string replacement in the query

This ensures tokens are always correctly formed, never duplicated, and the mapping is always consistent.

### 4.4 Dates — Special Handling

Exact dates are PHI under HIPAA Safe Harbor (year is allowed). The gatekeeper converts dates to relative descriptions:

- "January 15, 2026" → "approximately 2 months ago"
- "March 2024" → "approximately 2 years ago"
- "2019" → "2019" (year alone is allowed)

This conversion happens at the gatekeeper level before the sanitized query reaches the cloud. The relative description preserves temporal reasoning capability for the cloud model while removing the identifier.

---

## 5. Cloud Model Integration

### 5.1 Multi-Provider Adapter

Each cloud provider has a different API format for tool calling. The GX10 backend implements a thin adapter layer:

```
CloudAdapter (abstract)
  ├── ClaudeAdapter
  │     - Uses Anthropic Messages API
  │     - Tool use via tools parameter with input_schema
  │     - Model: claude-sonnet-4-20250514 or latest available
  ├── OpenAIAdapter
  │     - Uses OpenAI Chat Completions API
  │     - Tool use via functions/tools parameter
  │     - Model: gpt-4o or latest available
  └── GeminiAdapter
        - Uses Google Generative AI API
        - Tool use via function_declarations
        - Model: gemini-2.0-flash or latest available
```

Each adapter implements:
- `send_query(sanitized_query, system_prompt, tools) → response`
- `parse_tool_call(response) → {tool_name, arguments}` (for gatekeeper callbacks)
- `send_tool_result(result) → response` (to continue the conversation)

The adapters handle the format differences. The rest of the system is provider-agnostic.

### 5.2 Cloud Model System Prompt

The cloud model receives a system prompt that explains its role and available tools. Draft:

```
You are a clinical AI assistant. You help healthcare professionals with 
diagnostic reasoning, record review, and clinical decision support.

You are connected to a clinical knowledge base through the "query_gatekeeper" 
tool. Patient identifiers are redacted — you will see tokens like [PATIENT_1], 
[PROVIDER_1], etc. These are privacy placeholders. Use them naturally in your 
responses without attempting to guess real identities.

You will also see citation tokens like [REF_1], [REF_2] next to facts. Always 
include these in your response when referencing those facts — they allow the 
clinician to verify your claims against source documents.

IMPORTANT WORKFLOW:
Before providing a diagnosis or clinical recommendation, ALWAYS gather 
sufficient context. At minimum, request:
1. Relevant lab results
2. Family history 
3. Current medication list
Use the query_gatekeeper tool for each. You may query it additional times if 
you need more information (imaging results, procedure history, vital trends, 
specialist notes, etc.).

Only provide your clinical assessment after you have gathered enough context 
to reason carefully.

Do not fabricate clinical data. If the gatekeeper reports that information is 
not available, acknowledge the gap in your response.
```

**The "always request 3 things" instruction** is a demo reliability measure. It ensures the cloud model makes 2–4 gatekeeper queries per interaction, which: (a) creates a visually interesting multi-turn exchange, (b) demonstrates the gatekeeper's knowledge retrieval capability, and (c) lights up the graph traversal visualization multiple times.

### 5.3 Tool Definition

The cloud model gets one tool:

```json
{
  "name": "query_gatekeeper",
  "description": "Query the clinical knowledge base for patient information. The gatekeeper will return redacted clinical data with citation tokens. You can ask for: lab results, medication history, family history, visit history, imaging results, procedure history, vital signs, specialist notes, or any other clinical context about a patient. Use patient tokens (e.g., [PATIENT_1]) in your query.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Your question to the clinical knowledge base, using patient tokens"
      }
    },
    "required": ["query"]
  }
}
```

The cloud model calls this tool with natural language queries like: "What are [PATIENT_1]'s most recent lab results?" The GX10 backend intercepts the tool call, routes it to the gatekeeper, and returns the redacted response as the tool result.

---

## 6. Citation System

### 6.1 Reference Token Format

The gatekeeper assigns opaque reference tokens `[REF_N]` where N increments from 1 for each interaction. The cloud model sees ONLY these tokens — no document names, no page numbers, no file paths.

Example gatekeeper response to the cloud model:
```
[PATIENT_1], 31, male. ANA positive 1:640 [REF_1], ESR 48 mm/hr [REF_2], 
CBC within normal limits [REF_3]. Prescribed hydroxychloroquine 200mg 
approximately 3 months ago [REF_4]. Mother had rheumatoid arthritis [REF_5].
```

Internal reference mapping (never sent to cloud):
```json
{
  "[REF_1]": {"pdf": "/data/pdfs/lab_report_smith_2025_oct.pdf", "page": 2},
  "[REF_2]": {"pdf": "/data/pdfs/lab_report_smith_2025_oct.pdf", "page": 2},
  "[REF_3]": {"pdf": "/data/pdfs/lab_report_smith_2025_oct.pdf", "page": 3},
  "[REF_4]": {"pdf": "/data/pdfs/progress_note_smith_2026_jan.pdf", "page": 1},
  "[REF_5]": {"pdf": "/data/pdfs/intake_form_smith_2024.pdf", "page": 4}
}
```

### 6.2 Re-Hydration of Citations

During re-hydration, each `[REF_N]` in the cloud model's final response is replaced with a clickable citation object in the frontend. The frontend renders these as inline superscript links (e.g., `[1]`, `[2]`) or as styled citation markers. Clicking one opens the PDF viewer to the specific page.

The re-hydrated citation object sent to the frontend:
```json
{
  "ref_id": "REF_1",
  "display": "Lab Report — Oct 2025, p.2",
  "pdf_path": "/data/pdfs/lab_report_smith_2025_oct.pdf",
  "page": 2
}
```

### 6.3 PDF Viewer

When a citation is clicked (or when a graph node's source PDF is opened), a PDF viewer overlays the right panel (replacing the 3D graph temporarily). Implementation options:

- **pdf.js** (Mozilla) — widely used, renders PDFs in the browser, supports page navigation. Can open directly to a specific page number.
- **react-pdf** — React wrapper around pdf.js. If the frontend is React-based, this is the simplest integration.

The viewer opens to the cited page. A "Close" button returns to the 3D graph view. No need for fancy text highlighting for the hackathon — page-level navigation is sufficient.

---

## 7. Frontend

### 7.1 Tech Stack Decision

The frontend is a **web application** served by the GX10 backend. The clinician accesses it via browser on any device on the hospital network.

Recommended stack for hackathon:
- **React** (or Next.js if SSR is useful) for the chat UI and layout
- **Three.js via 3d-force-graph** for the 3D knowledge graph visualization
- **react-pdf or pdf.js** for the PDF viewer
- **WebSocket or SSE** for streaming responses from the GX10 backend (so the chat doesn't block while the cloud model is reasoning and querying the gatekeeper)

Alternative if the team prefers simplicity: a plain HTML/JS frontend with no framework. The 3d-force-graph library works standalone without React.

### 7.2 Layout

```
┌─────────────────────────────────┬─────────────────────────────────┐
│         LEFT PANEL (50%)        │        RIGHT PANEL (50%)        │
│                                 │                                 │
│   Chat Interface                │   3D Knowledge Graph            │
│   - Message history             │   OR                            │
│   - Input box at bottom         │   PDF Viewer (when citation     │
│   - Model selector dropdown     │     or node source is clicked)  │
│   - Inline citation links       │                                 │
│                                 │   "Close" button returns        │
│                                 │   to graph view                 │
└─────────────────────────────────┴─────────────────────────────────┘
```

The **redacted view** is either:
- A third panel below (if screen space permits)
- A toggleable overlay/tab
- Displayed on a second monitor during the live demo

For the demo, a second monitor is most impactful — the audience sees the clinician view on one screen and the "what the cloud sees" view on another simultaneously.

### 7.3 Data Flow from Frontend Perspective

```
1. User types query → frontend sends to GX10 backend (POST /api/query)
2. Frontend enters "thinking" state, shows typing indicator
3. GX10 backend streams events back via WebSocket/SSE:
   a. { type: "deidentified_query", content: "[PATIENT_1] presenting with..." }
      → Frontend shows this in the redacted view
   b. { type: "cloud_thinking", content: "Requesting lab results..." }
      → Frontend shows intermediate step in chat
   c. { type: "gatekeeper_query", content: "Lab results for [PATIENT_1]?" }
      → Frontend shows in redacted view
   d. { type: "graph_traversal", nodes: ["patient_001", "lab_045", "lab_046"] }
      → Frontend highlights these nodes in the 3D graph
   e. { type: "gatekeeper_response", content: "ANA positive [REF_1]..." }
      → Frontend shows in redacted view
   f. (repeat c-e for additional gatekeeper queries)
   g. { type: "final_response", content: "Based on John Smith's history..." , 
        citations: [{ref_id: "REF_1", display: "...", pdf_path: "...", page: N}] }
      → Frontend renders the re-hydrated response with clickable citations
4. Frontend exits "thinking" state
```

---

## 8. 3D Knowledge Graph Visualization

### 8.1 Library

**3d-force-graph** — a thin wrapper around Three.js specifically for force-directed 3D graph rendering. Feed it nodes and edges as JSON; it handles physics simulation and rendering. Supports: click handlers on nodes, custom node colors/sizes, custom edge colors, camera controls (rotate, zoom, pan).

Repository: https://github.com/vasturiano/3d-force-graph

### 8.2 Node Visual Design

| Node Type | Color | Size | Shape |
|---|---|---|---|
| Patient | Blue (#4A90D9) | Large | Sphere |
| Visit | Yellow (#F5C542) | Medium | Sphere |
| Condition | Red (#E74C3C) | Medium | Sphere |
| Medication | Green (#2ECC71) | Medium | Sphere |
| Lab Result | Purple (#9B59B6) | Small | Sphere |
| Procedure | Orange (#E67E22) | Medium | Sphere |
| Provider | Teal (#1ABC9C) | Medium | Sphere |

Edges are thin lines colored light gray by default.

### 8.3 Traversal Path Highlighting

When the gatekeeper traverses the graph to answer a query, the backend emits `graph_traversal` events listing the node IDs being accessed. The frontend:

1. Receives the node list
2. Animates a **gold pulse** (#FFD700) along the edges connecting those nodes
3. Increases brightness/saturation of the accessed nodes
4. Leaves the accessed nodes slightly brighter than default after the pulse completes

By the end of a multi-turn interaction, the audience can visually see which parts of the graph were accessed — a cluster of illuminated nodes around the queried patient.

### 8.4 Node Click Behavior

Clicking a node shows an **info card** (a floating panel or tooltip) with the node's contents. The info card shows:
- Node type and display name (e.g., "Patient: John Smith", "Lab: ANA Panel")
- Key fields (age, condition status, lab values, etc.)
- A "View Source PDF" button (if the node has a `source_pdf` field)

Clicking "View Source PDF" opens the PDF viewer in the right panel, replacing the graph temporarily.

### 8.5 Ingestion Animation

Played at demo start. The animation:
1. Shows PDF document icons appearing one by one (or in small batches)
2. Each PDF "dissolves" into particles that fly to positions in the graph
3. Nodes materialize and edges draw in as connections are established
4. The full graph settles into its force-directed layout

This is purely visual — the graph data is already loaded. The animation is a scripted sequence layered on top of the pre-built graph, revealing nodes and edges progressively over ~15–30 seconds.

---

## 9. GX10 Backend

### 9.1 Tech Stack

The GX10 backend is a **Python server** (FastAPI recommended) running locally on the GX10. It:
- Serves the frontend static files
- Exposes a WebSocket/SSE endpoint for chat
- Runs the gatekeeper model via Ollama's API (localhost)
- Holds the knowledge graph in memory
- Manages ephemeral token mappings
- Calls cloud AI APIs via the adapter layer
- Streams events to the frontend for the redacted view and graph traversal

**Why Python:** Fastest to build for a hackathon, best library support for LLM integration (Anthropic SDK, OpenAI SDK, Google GenAI SDK), and FastAPI gives us WebSocket support with minimal boilerplate.

Alternative: Node.js/TypeScript if the team prefers a single language with the frontend.

### 9.2 API Endpoints

```
POST /api/query
  Body: { message: string, model: "claude" | "gpt4" | "gemini" }
  Response: WebSocket/SSE stream of events (see section 7.3)

GET /api/graph
  Response: { nodes: [...], edges: [...] }
  Returns the full knowledge graph for the 3D visualization

GET /api/pdf/:filename?page=N
  Response: PDF file (served from local storage)
  Used by the frontend PDF viewer

GET /api/models
  Response: ["claude", "gpt4", "gemini"]
  Returns available model options for the dropdown

POST /api/switch-model
  Body: { model: "claude" | "gpt4" | "gemini" }
  Response: { success: true }
  Switches the active model for subsequent queries
```

### 9.3 Query Processing Pipeline (Pseudocode)

```python
async def handle_query(user_message: str, model: str):
    # Step 1: De-identify the user's query
    phi_spans = await gatekeeper.identify_phi(user_message)
    token_mapping = generate_token_mapping(phi_spans)
    sanitized_query = apply_token_mapping(user_message, token_mapping)
    
    emit_event("deidentified_query", sanitized_query)
    
    # Step 2: Initialize reference mapping
    ref_mapping = {}
    ref_counter = 1
    
    # Step 3: Send to cloud model with tool access
    adapter = get_adapter(model)
    conversation = [{"role": "user", "content": sanitized_query}]
    
    while True:
        response = await adapter.send(conversation, tools=[gatekeeper_tool])
        
        if response.has_tool_call("query_gatekeeper"):
            # Step 4: Handle gatekeeper callback
            query = response.tool_call.arguments["query"]
            emit_event("gatekeeper_query", query)
            
            # Resolve tokens, traverse graph, compose response
            graph_results = traverse_graph(query, token_mapping)
            emit_event("graph_traversal", graph_results.accessed_nodes)
            
            redacted_response, new_refs = redact_and_cite(
                graph_results, token_mapping, ref_counter
            )
            ref_mapping.update(new_refs)
            ref_counter += len(new_refs)
            
            emit_event("gatekeeper_response", redacted_response)
            
            # Feed result back to cloud model
            conversation.append(response.message)
            conversation.append(tool_result(redacted_response))
        
        else:
            # Step 5: Cloud model gave final response
            cloud_response = response.text
            emit_event("cloud_final_redacted", cloud_response)
            
            # Step 6: Re-hydrate
            final = rehydrate(cloud_response, token_mapping, ref_mapping)
            emit_event("final_response", final)
            
            # Step 7: Destroy mappings
            del token_mapping
            del ref_mapping
            
            break
```

---

## 10. Mock Data Generation

### 10.1 Strategy

Use Claude or GPT-4 to batch-generate synthetic clinical documents. The pipeline:

1. **Design patient profiles** — Create 30–40 fictional patients with varying complexity. Each profile defines: name, age, sex, conditions, medication history, visit history outline, family history, and primary storyline (e.g., "chronic fatigue leading to lupus diagnosis over 12 months").

2. **Generate documents per patient** — For each patient, generate the specific clinical documents their profile calls for. A complex patient might need: initial intake form, 4 progress notes, 3 lab reports, 1 imaging report, 1 specialist referral, 1 discharge summary = 11 documents. A simple patient might need 2–3.

3. **Convert to PDF** — Use a PDF generation library (reportlab, WeasyPrint, or Markdown → PDF via pandoc) to convert the generated text into realistic-looking clinical PDFs with headers, dates, patient info blocks, etc.

4. **Extract to knowledge graph** — Run NER/extraction (can use Claude or GPT-4 for this offline step) over each document to produce structured node/edge JSON. This step also records source_pdf and source_page per extracted fact.

5. **Validate** — Manually review a sample of generated documents and graph nodes to ensure consistency (same patient referenced across documents has consistent details).

### 10.2 Patient Distribution

Target: ~300 documents across 30–40 patients.

- **5–8 complex patients** (15–25 docs each): chronic conditions, multi-year histories, multiple specialists, changing medications. These are the demo showcase patients.
- **10–15 moderate patients** (5–10 docs each): a few visits, a condition or two, some labs.
- **15–20 simple patients** (2–3 docs each): single visit, straightforward presentation.

This distribution creates a realistic-looking graph where some patient clusters are dense and others are sparse.

### 10.3 Demo Showcase Patient

At least one patient should be specifically designed for the demo scenario — a complex case where symptoms accrue over multiple visits and converge on a specific diagnosis. The demo patient should:
- Have 15+ documents spanning 8–12 months
- Present with individually mild symptoms that together suggest a specific condition
- Have lab results that are diagnostically significant but not immediately obvious
- Have family history that supports the diagnosis
- Result in a differential diagnosis that frontier models reliably identify

Test this patient's documents against Claude, GPT-4, and Gemini 20+ times to confirm all three models produce interesting, multi-turn reasoning before committing to it as the demo case.

---

## 11. Demo Reliability

### 11.1 Managing Model Unpredictability

The cloud model's behavior cannot be scripted. Mitigation:

- **System prompt shaping:** The cloud model is instructed to always request lab results, family history, and medication history before forming a differential. This creates a predictable 2–4 turn structure without scripting content.

- **Pre-tested scenario:** The demo patient and scenario are tested extensively beforehand. The team selects a case that reliably produces interesting reasoning across all three models.

- **Fallback recording:** A screen recording of a successful demo run is prepared. If the live demo goes off-script, the presenter can say "Let me show you a full run we recorded earlier" and play it.

- **Graceful narration:** If the model does something unexpected during live demo (asks a different question, gives answer too quickly), the presenter narrates around it: "As you can see, the model decided it had enough context — in other runs, it asked more questions, but the privacy architecture works the same regardless."

### 11.2 Latency Considerations

The demo involves multiple round trips: user → GX10 → cloud → GX10 → cloud (repeat) → GX10 → user. Each cloud API call adds 2–10 seconds depending on the model and response length.

A full interaction with 3 gatekeeper queries might take 15–30 seconds total. This is fine for a demo — the graph traversal animation, redacted view updates, and intermediate "thinking" indicators keep the audience engaged during processing.

The gatekeeper's local inference (on-device) should be fast — under 3 seconds per query for a 27B model on the Blackwell GPU. This is not the bottleneck; the cloud API calls are.

---

## 12. File Structure (Proposed)

```
medgate/
├── README.md
├── PRODUCT_DESCRIPTION.md          # PRD (source of truth for product)
├── TECHNICAL.md                    # This document
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 # Main layout (chat + graph panels)
│   │   ├── ChatPanel.jsx           # Chat interface
│   │   ├── GraphPanel.jsx          # 3D knowledge graph
│   │   ├── PdfViewer.jsx           # PDF viewer overlay
│   │   ├── RedactedView.jsx        # Secondary display
│   │   ├── ModelSelector.jsx       # Dropdown for model switching
│   │   └── CitationLink.jsx        # Clickable citation component
│   └── package.json
├── backend/
│   ├── server.py                   # FastAPI main server
│   ├── gatekeeper.py               # Gatekeeper logic (PHI detection, graph query, redaction)
│   ├── token_manager.py            # Ephemeral token mapping lifecycle
│   ├── graph.py                    # Knowledge graph loading and traversal
│   ├── adapters/
│   │   ├── base.py                 # Abstract cloud adapter
│   │   ├── claude_adapter.py       # Anthropic API
│   │   ├── openai_adapter.py       # OpenAI API
│   │   └── gemini_adapter.py       # Google GenAI API
│   ├── citation.py                 # REF token management and re-hydration
│   └── requirements.txt
├── data/
│   ├── graph.json                  # Pre-built knowledge graph
│   ├── pdfs/                       # Source PDF documents (~300 files)
│   └── patients/                   # Patient profile definitions (used for generation)
├── scripts/
│   ├── generate_patients.py        # Generate patient profiles
│   ├── generate_documents.py       # Generate synthetic clinical docs
│   ├── build_graph.py              # Extract entities and build graph.json
│   └── test_demo_scenario.py       # Automated testing of demo case across models
└── prompts/
    ├── gatekeeper_system.txt       # Gatekeeper system prompt
    └── cloud_model_system.txt      # Cloud model system prompt
```

---

*This document captures technical decisions as of 2026-03-28. It should be updated as implementation progresses and decisions are revised. For product-level requirements, defer to PRODUCT_DESCRIPTION.md.*