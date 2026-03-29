# MedGate

**Privacy-preserving clinical AI that lets hospitals use frontier cloud models (Claude, GPT-4, Gemini) on sensitive patient data without violating HIPAA.**

PHI never leaves the hospital. A local gatekeeper LLM strips identifiers, the sanitized query goes to the cloud, and responses are re-hydrated with real data before reaching the clinician.

Built at [YHacks 2026](https://www.yhack.org/) on the [ASUS Ascent GX10](https://www.asus.com/motherboards-components/graphics-cards/proart/asus-ascent-gx10/) (NVIDIA GB10 Blackwell).

---

## How It Works

```
Clinician query
    |
    v
[Local Gatekeeper LLM]  ── strips PHI, generates ephemeral tokens
    |
    v
"What's [PATIENT_1]'s history? Headaches + fatigue for [DATE_1]"
    |
    v
[Cloud Model]  ── reasons on de-identified data, requests context via tool-use
    |                         |
    |                  [Gatekeeper answers]
    |                  graph queries with
    |                  redacted results +
    |                  citation tokens
    v
[Rehydration]  ── tokens → real names, dates, citations → PDF links
    |
    v
Clinician sees full response with clickable source documents
    |
    v
Token mapping destroyed (no persistence)
```

**HIPAA Safe Harbor compliant** — all 18 identifiers are removed before any data leaves the local device. Clinical facts (diagnoses, labs, medications) are preserved since they aren't PHI.

## Features

- **Multi-model support** — switch between Claude, GPT-4, and Gemini mid-conversation
- **3D knowledge graph** — interactive force-directed visualization of ~1,075 clinical entities (patients, visits, conditions, labs, medications, procedures, providers, family history)
- **Citation tracking** — every claim links back to the source PDF and page number
- **In-browser PDF viewer** — click a citation to open the document at the exact page
- **Real-time graph traversal** — nodes pulse and highlight as the gatekeeper retrieves data
- **Ephemeral token system** — PHI mappings exist only for the duration of a single interaction
- **Web search tool** — cloud models can query Wikipedia for medical reference information

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 8, 3d-force-graph (Three.js), react-pdf |
| Backend | Python 3.9+, FastAPI, Uvicorn |
| Local LLM | Ollama (Mistral Small 24B / Qwen 2.5 32B / Gemma 2 27B) |
| Cloud AI | Anthropic (Claude), OpenAI (GPT-4), Google (Gemini) |
| Data | JSON knowledge graph (~1,075 nodes, ~7,000 edges), ~300 synthetic clinical PDFs |
| Hardware | ASUS Ascent GX10 — NVIDIA GB10 Blackwell, 128GB unified LPDDR5x, 1TB NVMe |

## Project Structure

```
yale-hacks/
├── backend/
│   ├── server.py              # FastAPI server, SSE orchestration
│   ├── gatekeeper.py          # PHI detection, graph queries, rehydration
│   ├── graph.py               # Knowledge graph loading & traversal
│   ├── token_manager.py       # Ephemeral PHI ↔ token mapping
│   ├── citation.py            # Citation token management
│   ├── web_search.py          # Wikipedia search tool
│   ├── adapters/
│   │   ├── base.py            # Abstract cloud adapter
│   │   ├── claude_adapter.py  # Anthropic API
│   │   ├── openai_adapter.py  # OpenAI API
│   │   └── gemini_adapter.py  # Google GenAI API
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx            # Main layout, state management
│   │   ├── ChatPanel.jsx      # Chat UI, markdown rendering
│   │   ├── GraphPanel.jsx     # 3D knowledge graph visualization
│   │   ├── PdfViewer.jsx      # PDF overlay viewer
│   │   └── RedactedView.jsx   # "What the cloud sees" display
│   ├── dist/                  # Pre-built production bundle
│   └── package.json
├── data/
│   ├── graph.json             # Full knowledge graph
│   ├── pdfs/                  # ~300 synthetic clinical PDFs
│   └── patients/              # Patient profile definitions
├── scripts/
│   ├── generate_profiles.py   # Create synthetic patient profiles
│   ├── generate_documents.py  # Generate clinical PDFs
│   └── build_graph.py         # Build knowledge graph from PDFs
├── eval/                      # Model comparison & benchmarks
├── tests/                     # Pytest suite
├── docs/                      # Technical documentation
└── PRD.md                     # Product requirements
```

## Getting Started

### Prerequisites

- Python 3.9+
- Node.js 18+ (for frontend development only)
- [Ollama](https://ollama.com/) with a gatekeeper model pulled (e.g. `ollama pull mistral-small:24b`)
- API keys for at least one cloud provider (Anthropic, OpenAI, or Google)

### Setup

```bash
# Clone the repo
git clone https://github.com/Slava-code/yale-hacks.git
cd yale-hacks

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend (only needed if modifying the UI)
cd ../frontend
npm install
npm run build
```

### Running

```bash
# Make sure Ollama is running with a gatekeeper model loaded
ollama run qwen2.5:32b

# Start the server (from repo root)
uvicorn backend.server:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser. The frontend is served from the pre-built `frontend/dist/` directory.

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key |
| `OPENAI_API_KEY` | GPT-4 API key |
| `GOOGLE_API_KEY` | Gemini API key |
| `OLLAMA_URL` | Ollama server URL (default: `http://localhost:11434`) |
| `GATEKEEPER_MODEL` | Local LLM model name (default: `qwen2.5:32b`) |
| `GRAPH_PATH` | Path to knowledge graph JSON |
| `PDF_DIR` | Path to clinical PDFs directory |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/query` | Submit a clinical query, returns SSE stream |
| `GET` | `/api/graph` | Full knowledge graph for visualization |
| `GET` | `/api/pdf/{filename}` | Serve a source PDF (supports `?page=N`) |
| `GET` | `/api/models` | List available cloud models |

## Testing

```bash
cd backend
source venv/bin/activate
pytest ../tests/ -v
```

## Architecture Docs

- [PRD.md](PRD.md) — product requirements (source of truth)
- [TECHNICAL.md](TECHNICAL.md) — technical architecture index
- [docs/backend.md](docs/backend.md) — gatekeeper, token system, cloud adapters
- [docs/knowledge-graph.md](docs/knowledge-graph.md) — graph schema and data generation
- [docs/frontend.md](docs/frontend.md) — UI components and interactions
- [docs/interfaces.md](docs/interfaces.md) — REST endpoints, SSE events, data contracts
- [docs/deployment.md](docs/deployment.md) — GX10 setup and deployment

## Privacy & Compliance

MedGate implements **HIPAA Safe Harbor de-identification** (45 CFR 164.514):

| Stripped (replaced with tokens) | Preserved (not PHI) |
|--------------------------------|---------------------|
| Patient names | Age (except 90+) |
| MRNs, SSNs | Sex / gender |
| Dates (converted to relative) | Diagnoses, symptoms |
| Addresses, phone, email | Lab results |
| Provider names | Medications, procedures |

Token mappings are ephemeral — created per interaction and destroyed immediately after response delivery. No PHI is ever persisted outside the local system or transmitted to cloud providers.

## Team

Built at YHacks 2026 by Kevin Rusagara, Slava, and team.

## License

This project was built for a hackathon. See the repository for license details.
