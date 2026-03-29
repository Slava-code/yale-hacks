# MedGate — Frontend Technical Spec

**Parent:** [TECHNICAL.md](../TECHNICAL.md) §4
**Owner:** Frontend developer(s)
**Last updated:** 2026-03-28

This document covers the chat interface, 3D knowledge graph visualization, citation system rendering, and PDF viewer. For product requirements, see [PRD.md](../PRD.md).

---

## 1. Tech Stack

The frontend is a **web application** served by the GX10 backend. The clinician accesses it via browser on any device on the hospital network.

Recommended stack for hackathon:
- **React** (or Next.js if SSR is useful) for the chat UI and layout
- **Three.js via 3d-force-graph** for the 3D knowledge graph visualization
- **react-pdf or pdf.js** for the PDF viewer
- **WebSocket or SSE** for streaming responses from the GX10 backend (so the chat doesn't block while the cloud model is reasoning and querying the gatekeeper)

Alternative if the team prefers simplicity: a plain HTML/JS frontend with no framework. The 3d-force-graph library works standalone without React.

---

## 2. Layout

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

---

## 3. Data Flow from Frontend Perspective

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

## 4. Citation System (Frontend Rendering)

### 4.1 Reference Token Format

The backend handles all token mapping. The frontend receives the final re-hydrated response where each `[REF_N]` has been replaced with a citation object:

```json
{
  "ref_id": "REF_1",
  "display": "Lab Report — Oct 2025, p.2",
  "pdf_path": "/data/pdfs/lab_report_smith_2025_oct.pdf",
  "page": 2
}
```

The frontend renders these as inline superscript links (e.g., `[1]`, `[2]`) or as styled citation markers. Clicking one opens the PDF viewer to the specific page.

### 4.2 PDF Viewer

When a citation is clicked (or when a graph node's source PDF is opened), a PDF viewer overlays the right panel (replacing the 3D graph temporarily). Implementation options:

- **pdf.js** (Mozilla) — widely used, renders PDFs in the browser, supports page navigation. Can open directly to a specific page number.
- **react-pdf** — React wrapper around pdf.js. If the frontend is React-based, this is the simplest integration.

The viewer opens to the cited page. A "Close" button returns to the 3D graph view. No need for fancy text highlighting for the hackathon — page-level navigation is sufficient.

---

## 5. 3D Knowledge Graph Visualization

### 5.1 Library

**3d-force-graph** — a thin wrapper around Three.js specifically for force-directed 3D graph rendering. Feed it nodes and edges as JSON; it handles physics simulation and rendering. Supports: click handlers on nodes, custom node colors/sizes, custom edge colors, camera controls (rotate, zoom, pan).

Repository: https://github.com/vasturiano/3d-force-graph

### 5.2 Node Visual Design

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

### 5.3 Traversal Path Highlighting

When the gatekeeper traverses the graph to answer a query, the backend emits `graph_traversal` events listing the node IDs being accessed. The frontend:

1. Receives the node list
2. Animates a **gold pulse** (#FFD700) along the edges connecting those nodes
3. Increases brightness/saturation of the accessed nodes
4. Leaves the accessed nodes slightly brighter than default after the pulse completes

By the end of a multi-turn interaction, the audience can visually see which parts of the graph were accessed — a cluster of illuminated nodes around the queried patient.

### 5.4 Node Click Behavior

Clicking a node shows an **info card** (a floating panel or tooltip) with the node's contents. The info card shows:
- Node type and display name (e.g., "Patient: John Smith", "Lab: ANA Panel")
- Key fields (age, condition status, lab values, etc.)
- A "View Source PDF" button (if the node has a `source_pdf` field)

Clicking "View Source PDF" opens the PDF viewer in the right panel, replacing the graph temporarily.

### 5.5 Ingestion Animation

Played at demo start. The animation:
1. Shows PDF document icons appearing one by one (or in small batches)
2. Each PDF "dissolves" into particles that fly to positions in the graph
3. Nodes materialize and edges draw in as connections are established
4. The full graph settles into its force-directed layout

This is purely visual — the graph data is already loaded. The animation is a scripted sequence layered on top of the pre-built graph, revealing nodes and edges progressively over ~15–30 seconds.

---

## 6. File Structure (Frontend)

```
frontend/
├── src/
│   ├── App.jsx                 # Main layout, header, model selector (inline)
│   ├── components/
│   │   ├── ChatPanel.jsx       # Chat interface + inline citation rendering
│   │   ├── GraphPanel.jsx      # 3D knowledge graph
│   │   ├── PdfViewer.jsx       # PDF viewer overlay
│   │   ├── RedactedView.jsx    # Secondary display
│   │   └── IngestionAnimation.jsx  # Startup ingestion animation (demo)
│   └── index.css               # Global styles + CSS custom properties
└── package.json
```
