# MedGate — Demo & Project Reference

**Parent:** [TECHNICAL.md](../TECHNICAL.md) §1
**Owner:** Whole team
**Last updated:** 2026-03-28

This document covers the system architecture overview, demo reliability strategy, latency considerations, and the full project file structure. For product requirements, see [PRD.md](../PRD.md).

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

## 2. Demo Reliability

### 2.1 Managing Model Unpredictability

The cloud model's behavior cannot be scripted. Mitigation:

- **System prompt shaping:** The cloud model is instructed to always request lab results, family history, and medication history before forming a differential. This creates a predictable 2–4 turn structure without scripting content.

- **Pre-tested scenario:** The demo patient and scenario are tested extensively beforehand. The team selects a case that reliably produces interesting reasoning across all three models.

- **Fallback recording:** A screen recording of a successful demo run is prepared. If the live demo goes off-script, the presenter can say "Let me show you a full run we recorded earlier" and play it.

- **Graceful narration:** If the model does something unexpected during live demo (asks a different question, gives answer too quickly), the presenter narrates around it: "As you can see, the model decided it had enough context — in other runs, it asked more questions, but the privacy architecture works the same regardless."

- **Love scenario (YHack theme):** Valentine Torres (patient_041) is a lighthearted demo case where the diagnosis is "being in love." The frontend detects keywords like "in love", "diagnosis: love", "lovesick", or "love syndrome" in the final response (case-insensitive substring match in ChatPanel.jsx) and triggers a hearts overlay animation with a pink theme transition. The stub server selects this scenario when the query mentions "valentine", "racing heart", or "daydream." For the live demo, this is the crowd-pleasing finale — run it after the serious medical case to show the system's personality and tie into the hackathon theme.

### 2.2 Latency Considerations

The demo involves multiple round trips: user → GX10 → cloud → GX10 → cloud (repeat) → GX10 → user. Each cloud API call adds 2–10 seconds depending on the model and response length.

A full interaction with 3 gatekeeper queries might take 15–30 seconds total. This is fine for a demo — the graph traversal animation, redacted view updates, and intermediate "thinking" indicators keep the audience engaged during processing.

The gatekeeper's local inference (on-device) is fast but not instant — benchmarks show ~11-17 tok/s for 20-27B models when solo-loaded (see [speed benchmark](../eval/results/speed-benchmark-2026-03-28.md)). A typical 100-token gatekeeper response takes ~6-9 seconds. This is not the primary bottleneck; the cloud API calls (2-10 seconds each) still dominate total latency, but gatekeeper inference is no longer negligible.

---

## 3. Full Project File Structure

```
medgate/
├── CLAUDE.md                       # Claude Code guidelines (read first)
├── PRD.md                          # PRD (source of truth for product)
├── TECHNICAL.md                    # Technical architecture index (points to docs/)
├── docs/
│   ├── backend.md                  # Backend spec (gatekeeper, tokens, cloud adapters, API)
│   ├── knowledge-graph.md          # Knowledge graph schema + data generation
│   ├── frontend.md                 # Frontend spec (chat, 3D graph, PDF viewer, citations)
│   ├── interfaces.md               # Data contracts (REST, SSE events, graph API, conventions)
│   └── demo.md                     # This document (architecture, demo strategy, file structure)
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
│   ├── stub_server.py              # Stub server for frontend dev (hardcoded SSE scenario)
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
│   ├── patients/                   # Patient profile definitions (used for generation)
│   └── stub/
│       └── graph.json              # Small stub graph (5 patients) for frontend dev
├── scripts/
│   ├── generate_profiles.py        # Generate patient profiles
│   ├── generate_documents.py       # Generate synthetic clinical docs
│   ├── build_graph.py              # Extract entities and build graph.json
│   └── test_demo_scenario.py       # Automated testing of demo case across models
└── prompts/
    ├── gatekeeper_system.txt       # Gatekeeper system prompt
    └── cloud_model_system.txt      # Cloud model system prompt
```
