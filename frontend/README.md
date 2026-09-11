# MedGate frontend

The MedGate clinician UI: a React 19 + Vite single-page app with a chat panel on the left and a 3D knowledge graph (`3d-force-graph` / Three.js) or an in-browser PDF viewer (`react-pdf`) on the right. It talks to the FastAPI backend over `/api/*` and consumes the query SSE stream — see [`../docs/frontend.md`](../docs/frontend.md) and [`../docs/interfaces.md`](../docs/interfaces.md).

## Development

```bash
npm install
npm run dev     # Vite dev server on http://localhost:5173
```

The dev server proxies `/api/*` to `http://localhost:8000`, so run the backend (`uvicorn backend.server:app --port 8000`) alongside it. To develop against the GX10 instead, change the proxy `target` in `vite.config.js`. For UI work without a real backend, `backend/stub_server.py` serves the same endpoints with hardcoded SSE events.

## Build

```bash
npm run build   # -> dist/
```

FastAPI serves `dist/` as the production frontend. The hashed JS/CSS bundles are gitignored, so `dist/` must be built once on any fresh clone before the backend can serve the UI.

## Components

`src/App.jsx` owns the layout and shared state. Components live in `src/components/`, each with a matching `.css`:

| Component | Role |
|-----------|------|
| `ChatPanel.jsx` | Chat UI, SSE event handling, markdown rendering, citation chips |
| `GraphPanel.jsx` | 3D force-directed knowledge graph, traversal highlighting, node info cards |
| `PdfViewer.jsx` | PDF overlay, opens a cited document at the cited page |
| `RedactedView.jsx` | "What the cloud sees" — de-identified queries and gatekeeper exchanges |
| `IngestionAnimation.jsx` | Startup animation of the document corpus being ingested |
| `HeartsOverlay.jsx` | YHack theme easter egg, triggered when a response diagnoses love (the backend side is gated by `DEMO_EASTER_EGGS`) |
