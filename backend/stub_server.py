"""
MedGate Stub Server

A standalone FastAPI server that serves stub data and emits hardcoded SSE events.
Use this so the frontend can be built and tested without the real backend.

Run:
    pip install fastapi uvicorn
    uvicorn stub_server:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

app = FastAPI(title="MedGate Stub Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STUB_GRAPH_PATH = Path(__file__).parent.parent / "data" / "graph.json"

# --- Node visual config (matches docs/interfaces.md §4) ---

NODE_CONFIG = {
    "patient":    {"color": "#4A90D9", "size": 12},
    "visit":      {"color": "#F5C542", "size": 8},
    "condition":  {"color": "#E74C3C", "size": 8},
    "medication": {"color": "#2ECC71", "size": 8},
    "lab_result": {"color": "#9B59B6", "size": 6},
    "procedure":  {"color": "#E67E22", "size": 8},
    "provider":   {"color": "#1ABC9C", "size": 8},
    "family_history": {"color": "#D946EF", "size": 7},
    "disease_reference": {"color": "#3B82F6", "size": 7},
}


def _load_graph():
    """Load stub graph.json and transform to frontend format (flat metadata, no PHI wrappers)."""
    raw = json.loads(STUB_GRAPH_PATH.read_text())
    nodes = []
    for node in raw["nodes"].values():
        config = NODE_CONFIG.get(node["type"], {"color": "#999", "size": 6})
        metadata = {k: v["value"] for k, v in node.get("fields", {}).items()}
        nodes.append({
            "id": node["id"],
            "type": node["type"],
            "label": node["label"],
            "color": config["color"],
            "size": config["size"],
            "metadata": metadata,
            **({"source_pdf": node["source_pdf"], "source_page": node["source_page"]}
               if "source_pdf" in node else {}),
        })
    return {"nodes": nodes, "edges": raw["edges"]}


# --- Hardcoded SSE scenario (John Smith lupus case) ---

SSE_SCENARIO = [
    {
        "type": "deidentified_query",
        "data": {
            "type": "deidentified_query",
            "content": "[PATIENT_1], 31, male, presenting with recurring headaches and joint pain for approximately 8 months. What could be going on?",
            "token_summary": {"PATIENT_1": "patient_name"},
        },
        "delay": 0.5,
    },
    {
        "type": "cloud_thinking",
        "data": {
            "type": "cloud_thinking",
            "content": "Analyzing query and requesting clinical context...",
        },
        "delay": 1.0,
    },
    {
        "type": "gatekeeper_query",
        "data": {
            "type": "gatekeeper_query",
            "content": "What are the lab results for [PATIENT_1] from the past 12 months?",
            "turn": 1,
        },
        "delay": 1.5,
    },
    {
        "type": "graph_traversal",
        "data": {
            "type": "graph_traversal",
            "nodes": ["patient_001", "visit_003", "lab_001", "lab_002", "lab_003", "lab_006"],
            "edges": [
                {"source": "patient_001", "target": "visit_003"},
                {"source": "visit_003", "target": "lab_001"},
                {"source": "visit_003", "target": "lab_002"},
                {"source": "visit_003", "target": "lab_003"},
                {"source": "visit_003", "target": "lab_006"},
            ],
            "turn": 1,
        },
        "delay": 1.0,
    },
    {
        "type": "gatekeeper_response",
        "data": {
            "type": "gatekeeper_response",
            "content": "ANA positive, titer 1:320 [REF_1]. ESR elevated at 45 mm/hr [REF_2]. CBC: WBC 3.2 (low), Hgb 11.8 (low), Plt 135 (low) [REF_3]. Anti-dsDNA antibody elevated at 85 IU/mL [REF_4].",
            "turn": 1,
            "refs_added": ["REF_1", "REF_2", "REF_3", "REF_4"],
        },
        "delay": 1.5,
    },
    {
        "type": "gatekeeper_query",
        "data": {
            "type": "gatekeeper_query",
            "content": "What is the medication history for [PATIENT_1]?",
            "turn": 2,
        },
        "delay": 1.0,
    },
    {
        "type": "graph_traversal",
        "data": {
            "type": "graph_traversal",
            "nodes": ["patient_001", "medication_001", "condition_001"],
            "edges": [
                {"source": "patient_001", "target": "medication_001"},
                {"source": "condition_001", "target": "medication_001"},
            ],
            "turn": 2,
        },
        "delay": 0.8,
    },
    {
        "type": "gatekeeper_response",
        "data": {
            "type": "gatekeeper_response",
            "content": "Currently prescribed hydroxychloroquine 200mg twice daily [REF_5]. Started approximately 5 months ago for suspected autoimmune condition.",
            "turn": 2,
            "refs_added": ["REF_5"],
        },
        "delay": 1.5,
    },
    {
        "type": "gatekeeper_query",
        "data": {
            "type": "gatekeeper_query",
            "content": "What is the visit history and symptom progression for [PATIENT_1]?",
            "turn": 3,
        },
        "delay": 1.0,
    },
    {
        "type": "graph_traversal",
        "data": {
            "type": "graph_traversal",
            "nodes": ["patient_001", "visit_001", "visit_002", "visit_003", "provider_001"],
            "edges": [
                {"source": "patient_001", "target": "visit_001"},
                {"source": "patient_001", "target": "visit_002"},
                {"source": "patient_001", "target": "visit_003"},
                {"source": "visit_001", "target": "provider_001"},
            ],
            "turn": 3,
        },
        "delay": 0.8,
    },
    {
        "type": "gatekeeper_response",
        "data": {
            "type": "gatekeeper_response",
            "content": "Three visits over approximately 8 months. Initial visit [REF_6]: recurring bilateral frontal headaches, 3-4x/week. Second visit [REF_7]: headaches persisting, new morning joint stiffness in hands lasting ~45 minutes. Third visit [REF_8]: worsening bilateral joint pain (wrists, knees), new malar rash across bridge of nose. Referred to rheumatology [REF_8].",
            "turn": 3,
            "refs_added": ["REF_6", "REF_7", "REF_8"],
        },
        "delay": 2.0,
    },
    {
        "type": "final_response",
        "data": {
            "type": "final_response",
            "content": "Based on John Smith's clinical history, the combination of findings is strongly suggestive of **systemic lupus erythematosus (SLE)**.\n\n**Key supporting evidence:**\n\n1. **Malar rash** — The butterfly-pattern facial rash noted at the October visit [1] is one of the hallmark features of SLE.\n\n2. **Serological markers** — ANA titer of 1:320 [1] and anti-dsDNA antibody at 85 IU/mL [1] are both significantly elevated. Anti-dsDNA is highly specific for SLE.\n\n3. **Hematologic abnormalities** — Leukopenia (WBC 3.2), mild anemia (Hgb 11.8), and thrombocytopenia (Plt 135) [1] — cytopenias are a common SLE manifestation.\n\n4. **Inflammatory markers** — ESR of 45 mm/hr [2] indicates active systemic inflammation.\n\n5. **Symptom progression** — The 8-month trajectory from isolated headaches [6] to polyarticular joint involvement [7] to malar rash with serological confirmation [8] follows a classic SLE presentation pattern.\n\n6. **Demographics** — While SLE is more common in women, it does occur in men, typically with more severe organ involvement.\n\n**Recommendations:**\n- Continue hydroxychloroquine [5] — the current standard of care for SLE\n- Rheumatology follow-up for disease activity monitoring and potential immunosuppressive therapy\n- Monitor renal function (urinalysis, creatinine, complement levels) — lupus nephritis screening\n- Consider anti-Smith antibody and complement levels (C3/C4) for further serological characterization",
            "citations": [
                {"ref_id": "REF_1", "index": 1, "display": "Lab Report — Oct 2025, p.2", "pdf": "lab_report_smith_2025_oct.pdf", "page": 2},
                {"ref_id": "REF_2", "index": 2, "display": "Lab Report — Oct 2025, p.3", "pdf": "lab_report_smith_2025_oct.pdf", "page": 3},
                {"ref_id": "REF_3", "index": 3, "display": "Lab Report — Oct 2025, p.1", "pdf": "lab_report_smith_2025_oct.pdf", "page": 1},
                {"ref_id": "REF_4", "index": 4, "display": "Lab Report — Oct 2025, p.4", "pdf": "lab_report_smith_2025_oct.pdf", "page": 4},
                {"ref_id": "REF_5", "index": 5, "display": "Prescription Record", "pdf": "progress_note_smith_2025_oct.pdf", "page": 2},
                {"ref_id": "REF_6", "index": 6, "display": "Progress Note — Jun 2025, p.1", "pdf": "progress_note_smith_2025_jun.pdf", "page": 1},
                {"ref_id": "REF_7", "index": 7, "display": "Progress Note — Aug 2025, p.1", "pdf": "progress_note_smith_2025_aug.pdf", "page": 1},
                {"ref_id": "REF_8", "index": 8, "display": "Progress Note — Oct 2025, p.1", "pdf": "progress_note_smith_2025_oct.pdf", "page": 1}
            ],
            "model_used": "claude",
            "gatekeeper_turns": 3,
        },
        "delay": 0,
    },
]


# --- Endpoints ---

@app.get("/api/graph")
async def get_graph():
    return _load_graph()


@app.get("/api/models")
async def get_models():
    return {
        "models": [
            {"id": "claude", "name": "Claude", "available": True},
            {"id": "gpt4", "name": "GPT-4", "available": True},
            {"id": "gemini", "name": "Gemini", "available": True},
        ]
    }


@app.post("/api/query")
async def query(body: dict):
    """Streams hardcoded SSE events for the John Smith lupus scenario.
    Ignores the actual message/model — always returns the same scenario.
    """
    async def event_stream():
        for event in SSE_SCENARIO:
            await asyncio.sleep(event["delay"])
            yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/pdf/{filename}")
async def get_pdf(filename: str):
    """Stub: returns a 404-like message since we don't have real PDFs yet."""
    return {"error": f"Stub server — no real PDFs. Requested: {filename}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
