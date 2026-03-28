# MedGate — Technical Architecture Index

**Date:** 2026-03-28
**Status:** Draft
**Companion to:** `PRD.md` (source of truth for product requirements)

This document is the **index** for all technical decisions. Each major system component is described briefly below and links to a focused spec in `docs/`. Where a spec is silent, defer to the PRD. Where a spec specifies a technical approach, it takes precedence over assumptions.

---

## 1. System Architecture & Demo Strategy → [docs/demo.md](./docs/demo.md)

MedGate is a three-component system: a **custom frontend** (browser), a **GX10 backend** (local server with gatekeeper model + knowledge graph), and **cloud AI APIs** (Claude, GPT-4, Gemini). The GX10 backend mediates all communication — the frontend never contacts cloud APIs directly.

This spec also covers demo reliability (system prompt shaping, fallback recording, latency expectations) and the full proposed file structure for the project.

**Cross-references:** [backend.md](./docs/backend.md) (API endpoints, query pipeline), [frontend.md](./docs/frontend.md) (streaming events, layout)

---

## 2. GX10 Backend, Gatekeeper & Cloud Integration → [docs/backend.md](./docs/backend.md)

The GX10 runs a **Python/FastAPI** server that orchestrates the entire privacy pipeline. The local **gatekeeper model** (13B–27B parameters on the Blackwell GPU via Ollama) handles PHI identification and knowledge graph queries. **Deterministic code** handles token generation, graph traversal, string replacement, and re-hydration — the LLM is used only for natural language understanding, not for privacy-critical operations.

The backend also implements a **multi-provider cloud adapter** (Claude, GPT-4, Gemini) with a single tool (`query_gatekeeper`) that cloud models use to request clinical context. The **token mapping system** creates ephemeral per-interaction mappings that are destroyed after re-hydration.

Covers: GX10 hardware context, model selection & inference setup, gatekeeper system prompt, gatekeeper functions, token format & lifecycle, date handling, cloud adapter layer, cloud system prompt, tool definition, API endpoints, query processing pipeline.

**Cross-references:** [knowledge-graph.md](./docs/knowledge-graph.md) (graph schema the gatekeeper traverses), [frontend.md](./docs/frontend.md) (SSE events consumed by the UI), [demo.md](./docs/demo.md) (architecture diagram, latency)

---

## 3. Knowledge Graph & Mock Data → [docs/knowledge-graph.md](./docs/knowledge-graph.md)

The knowledge graph is stored as **in-memory JSON** — loaded once at startup, queried by the gatekeeper with zero disk I/O. The schema defines 7 node types (Patient, Visit, Condition, Medication, Lab Result, Procedure, Provider) and 9 edge types. Every node field is tagged `phi` or `safe` at construction time so the gatekeeper doesn't need real-time NER.

Mock data (~300 synthetic clinical PDFs across 30–40 patients) is generated via Claude/GPT-4, converted to PDF, then extracted into the graph with source provenance (file path + page number per node). At least one complex "demo showcase patient" is designed for the live demo scenario.

Covers: Storage format & rationale, node/edge schema, source provenance, PHI tagging, data generation pipeline, patient distribution, demo showcase patient design.

**Cross-references:** [backend.md](./docs/backend.md) (gatekeeper queries the graph), [frontend.md](./docs/frontend.md) (3D visualization of the graph), [demo.md](./docs/demo.md) (demo scenario uses the showcase patient)

---

## 4. Frontend (Chat, 3D Graph, Citations) → [docs/frontend.md](./docs/frontend.md)

The frontend is a **React** web app served by the GX10 backend. Layout: left panel (chat) + right panel (3D knowledge graph or PDF viewer). The **3D graph** uses `3d-force-graph` (Three.js) with color-coded nodes, click-to-inspect info cards, and real-time traversal path highlighting via SSE `graph_traversal` events. **Citations** are rendered as clickable inline links that open the PDF viewer (react-pdf/pdf.js) to the cited page.

A **redacted view** (second monitor or toggle) shows what the cloud model actually sees — de-identified queries, gatekeeper exchanges, and the final redacted response.

Covers: Tech stack, layout, SSE data flow, citation rendering, PDF viewer, 3D graph (library, node design, traversal highlighting, click behavior), ingestion animation, redacted view.

**Cross-references:** [backend.md](./docs/backend.md) (SSE events emitted by the server, API endpoints), [knowledge-graph.md](./docs/knowledge-graph.md) (graph data fed to the visualization), [demo.md](./docs/demo.md) (demo layout, ingestion animation)

---

## Environment & Configuration

| Key | Purpose | File |
|-----|---------|------|
| `GX10_HOST`, `GX10_USER`, `GX10_PASSWORD` | SSH/connection to the GX10 hardware | `.env` |
| `ANTHROPIC_API_KEY` | Claude API access | `.env` |
| `OPENAI_API_KEY` | GPT-4 API access | `.env` |
| `GOOGLE_API_KEY` | Gemini API access | `.env` |

See `.env.example` for the template. Never commit `.env` — it is gitignored.

---

*This document is the technical architecture index. For detailed specs, follow the links to `docs/`. For product requirements, see `PRD.md`. Last updated: 2026-03-28.*
