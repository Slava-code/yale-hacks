"""
MedGate Backend Server — FastAPI with SSE streaming.

Spec: docs/backend.md §5, docs/interfaces.md §1-2.

Orchestrates the full privacy pipeline:
  User query → gatekeeper de-identifies → cloud model reasons (with tool calls)
  → gatekeeper handles each tool call → cloud gives final answer
  → rehydrate → return to user

All events are streamed as SSE to the frontend.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.gatekeeper import Gatekeeper
from backend.token_manager import TokenMapping
from backend.citation import CitationManager
from backend.graph import load_graph, Graph, get_traversal_path
from backend.adapters.base import CloudAdapter
from backend.adapters.claude_adapter import ClaudeAdapter
from backend.adapters.openai_adapter import OpenAIAdapter
from backend.adapters.gemini_adapter import GeminiAdapter
from backend.web_search import web_search

load_dotenv()

app = FastAPI(title="MedGate Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Config ---

GRAPH_PATH = os.getenv("GRAPH_PATH", "data/stub/graph.json")
PDF_DIR = os.getenv("PDF_DIR", "data/pdfs")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
GATEKEEPER_MODEL = os.getenv("GATEKEEPER_MODEL", "qwen2.5:32b")

# Node visual config (matches docs/interfaces.md §4)
NODE_CONFIG = {
    "patient":           {"color": "#4A90D9", "size": 12},
    "visit":             {"color": "#F5C542", "size": 8},
    "condition":         {"color": "#E74C3C", "size": 8},
    "medication":        {"color": "#2ECC71", "size": 8},
    "lab_result":        {"color": "#9B59B6", "size": 6},
    "procedure":         {"color": "#E67E22", "size": 8},
    "provider":          {"color": "#1ABC9C", "size": 8},
    "family_history":    {"color": "#D946EF", "size": 7},
    "disease_reference": {"color": "#3B82F6", "size": 7},
}

# --- Globals (loaded once at startup) ---

_graph: Graph | None = None
_gatekeeper: Gatekeeper | None = None


def _get_graph() -> Graph:
    global _graph
    if _graph is None:
        _graph = load_graph(GRAPH_PATH)
    return _graph


def _get_gatekeeper() -> Gatekeeper:
    global _gatekeeper
    if _gatekeeper is None:
        _gatekeeper = Gatekeeper(ollama_url=OLLAMA_URL, model=GATEKEEPER_MODEL)
    return _gatekeeper


def _get_adapter(model: str) -> CloudAdapter:
    key_env_map = {
        "claude": "ANTHROPIC_API_KEY",
        "gpt4": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    env_var = key_env_map.get(model)
    if not env_var:
        raise ValueError(f"Unknown model: {model}")
    api_key = os.getenv(env_var, "")
    if not api_key:
        raise ValueError(f"API key not configured: set {env_var} environment variable")
    adapters = {
        "claude": lambda: ClaudeAdapter(api_key=api_key),
        "gpt4": lambda: OpenAIAdapter(api_key=api_key),
        "gemini": lambda: GeminiAdapter(api_key=api_key),
    }
    return adapters[model]()


# --- SSE helpers ---

def _format_sse_event(event_type: str, data: dict) -> str:
    """Format an SSE event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def _format_search_results(search_result: dict) -> str:
    """Format web search results as text for the cloud model."""
    parts = []
    for r in search_result.get("results", []):
        parts.append(f"=== {r['title']} ===\n{r['extract']}\nSource: {r['url']}")
    return "\n\n".join(parts) if parts else "No relevant results found."


# --- Graph API transform ---

def _load_graph_for_api() -> dict:
    """Transform graph to frontend format (flat metadata, no PHI wrappers)."""
    graph = _get_graph()
    nodes = []
    for node in graph.nodes.values():
        config = NODE_CONFIG.get(node.type, {"color": "#999", "size": 6})
        metadata = {k: v["value"] for k, v in node.fields.items()}
        entry = {
            "id": node.id,
            "type": node.type,
            "label": node.label,
            "color": config["color"],
            "size": config["size"],
            "metadata": metadata,
        }
        if node.source_pdf:
            entry["source_pdf"] = node.source_pdf
        if node.source_page is not None:
            entry["source_page"] = node.source_page
        nodes.append(entry)

    edges = [{"source": e["source"], "target": e["target"], "type": e["type"]}
             for e in graph.edges]

    return {"nodes": nodes, "edges": edges}


# --- Pipeline ---

async def _run_pipeline(
    message: str, model: str
) -> AsyncGenerator[tuple[str, dict], None]:
    """Run the full MedGate pipeline, yielding SSE events.

    Yields:
        (event_type, event_data) tuples
    """
    graph = _get_graph()
    gatekeeper = _get_gatekeeper()
    adapter = _get_adapter(model)

    # Step 1: De-identify
    deidentify_result = await gatekeeper.deidentify_query(message, graph)
    tm = deidentify_result["token_mapping"]
    patient_id = deidentify_result["patient_id"]
    cm = CitationManager()

    yield "deidentified_query", {
        "type": "deidentified_query",
        "content": deidentify_result["sanitized_query"],
        "token_summary": deidentify_result["token_summary"],
    }

    # Step 2: Cloud thinking
    yield "cloud_thinking", {
        "type": "cloud_thinking",
        "content": "Analyzing query and requesting clinical context...",
    }

    # Step 3: Send to cloud model with tool loop
    messages = [{"role": "user", "content": deidentify_result["sanitized_query"]}]
    turn = 0
    max_turns = 10  # safety limit

    # First call to cloud
    try:
        response = await adapter.send_query(messages)
    except Exception as e:
        yield "error", {
            "type": "error",
            "content": f"Cloud model API error: {str(e)}",
            "phase": "cloud_query",
        }
        return

    while turn < max_turns:
        # Parse the response — collect ALL tool calls (GPT-4 sends parallel calls)
        tool_calls = []
        text_content = ""

        for block in response.get("content", []):
            parsed = adapter.parse_tool_call(block)
            if parsed and parsed["tool_name"] in ("query_gatekeeper", "web_search"):
                tool_calls.append(parsed)
            elif block.get("type") == "text":
                text_content += block.get("text", "")

        if tool_calls:
            # Append assistant message ONCE before processing all tool calls
            messages.append(
                response.get("raw_message")
                or {"role": "assistant", "content": response.get("content", [])}
            )

            # Process each tool call and collect results
            # Each result is (tool_id, content, tool_name)
            tool_results = []
            for tool_call in tool_calls:
                turn += 1
                tool_name = tool_call["tool_name"]
                query = tool_call["arguments"].get("query", "")

                if tool_name == "query_gatekeeper":
                    yield "gatekeeper_query", {
                        "type": "gatekeeper_query",
                        "content": query,
                        "turn": turn,
                    }

                    kg_result = await gatekeeper.query_knowledge_graph(query, tm, graph, cm, patient_id=patient_id)

                    traversal = get_traversal_path(graph, kg_result["accessed_nodes"])
                    yield "graph_traversal", {
                        "type": "graph_traversal",
                        "nodes": [n.id for n in traversal.nodes],
                        "edges": traversal.edges,
                        "turn": turn,
                    }

                    yield "gatekeeper_response", {
                        "type": "gatekeeper_response",
                        "content": kg_result["content"],
                        "turn": turn,
                        "refs_added": kg_result["refs_added"],
                    }

                    tool_results.append((tool_call["tool_id"], kg_result["content"], "query_gatekeeper"))

                elif tool_name == "web_search":
                    yield "web_search_query", {
                        "type": "web_search_query",
                        "content": query,
                        "turn": turn,
                    }

                    search_result = await web_search(query)
                    result_text = _format_search_results(search_result)

                    yield "web_search_result", {
                        "type": "web_search_result",
                        "content": result_text,
                        "query": query,
                        "num_results": len(search_result["results"]),
                        "turn": turn,
                    }

                    tool_results.append((tool_call["tool_id"], result_text, "web_search"))

            # Send all tool results back to the cloud model
            try:
                if len(tool_results) == 1:
                    tid, content, tname = tool_results[0]
                    response = await adapter.send_tool_result(
                        messages, tid, content
                    )
                else:
                    for tid, content, tname in tool_results:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tid,
                            "content": content,
                            "name": tname,
                        })
                    response = await adapter.send_query(messages)
                continue
            except Exception as e:
                yield "error", {
                    "type": "error",
                    "content": f"Cloud model tool result error: {str(e)}",
                    "phase": "cloud_query",
                }
                return
        else:
            # Final response from cloud model
            if text_content:
                yield "cloud_response_chunk", {
                    "type": "cloud_response_chunk",
                    "content": text_content,
                    "done": True,
                }

            # Step 4: Rehydrate
            final = gatekeeper.rehydrate_response(text_content, tm, cm)

            yield "final_response", {
                "type": "final_response",
                "content": final["content"],
                "citations": final["citations"],
                "model_used": model,
                "gatekeeper_turns": turn,
            }
            return

    # Safety: max turns reached
    yield "error", {
        "type": "error",
        "content": "Maximum gatekeeper query turns reached.",
        "phase": "cloud_query",
    }


# --- Endpoints ---

class QueryRequest(BaseModel):
    message: str
    model: str


@app.post("/api/query")
async def query(req: QueryRequest):
    """Stream SSE events for a clinical query."""
    async def event_stream():
        async for event_type, event_data in _run_pipeline(req.message, req.model):
            yield _format_sse_event(event_type, event_data)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/graph")
async def get_graph():
    """Return the full knowledge graph for 3D visualization."""
    return _load_graph_for_api()


@app.get("/api/pdf/{filename}")
async def get_pdf(filename: str):
    """Serve a source PDF file."""
    pdf_path = Path(PDF_DIR) / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF not found: {filename}")
    return FileResponse(pdf_path, media_type="application/pdf")


@app.get("/api/models")
async def get_models():
    """Return available cloud model options."""
    return {
        "models": [
            {"id": "claude", "name": "Claude", "available": bool(os.getenv("ANTHROPIC_API_KEY"))},
            {"id": "gpt4", "name": "GPT-4", "available": bool(os.getenv("OPENAI_API_KEY"))},
            {"id": "gemini", "name": "Gemini", "available": bool(os.getenv("GEMINI_API_KEY"))},
        ]
    }


class SwitchModelRequest(BaseModel):
    model: str


@app.post("/api/switch-model")
async def switch_model(req: SwitchModelRequest):
    """Switch the active cloud model for subsequent queries."""
    valid = {"claude", "gpt4", "gemini"}
    if req.model not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid model: {req.model}. Must be one of {valid}")
    return {"success": True, "model": req.model}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# --- Static frontend (must be last — catches all non-API routes) ---

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
