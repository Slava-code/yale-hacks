"""
Demo pipeline stress tester — runs demo prompts against all 3 cloud models
via the live GX10 server and reports on quality, consistency, and failures.

Usage:
    python scripts/test_demo_pipeline.py [--runs N] [--host HOST:PORT]
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

DEFAULT_HOST = "100.84.219.15:8000"

DEMO_PROMPTS = [
    {
        "id": "demo_primary",
        "message": "Tell me about John Smith, he has been having recurring headaches",
        "description": "Primary demo: SLE progression from headaches",
        "expect_patient": True,
        "expect_min_turns": 2,
        "expect_keywords": ["headache", "lab", "ANA"],
    },
    {
        "id": "demo_family_history",
        "message": "What is the family history for John Smith?",
        "description": "Family history query — tests C4 fix",
        "expect_patient": True,
        "expect_min_turns": 1,
        "expect_keywords": ["family", "mother", "SLE"],
    },
    {
        "id": "demo_labs",
        "message": "Can you review John Smith's lab results and tell me if anything is concerning?",
        "description": "Lab review — should find ANA, inflammatory markers",
        "expect_patient": True,
        "expect_min_turns": 1,
        "expect_keywords": ["ANA", "ESR"],
    },
    {
        "id": "demo_full_workup",
        "message": "I need a full clinical assessment of John Smith. He presented with headaches months ago and symptoms have been evolving.",
        "description": "Full workup — should trigger 3-4 turns and SLE diagnosis",
        "expect_patient": True,
        "expect_min_turns": 3,
        "expect_keywords": ["SLE", "lupus"],
    },
    # --- Demo scenario 2: Marcus Reed / Zombie Virus ---
    {
        "id": "zombie_primary",
        "message": "Tell me about Marcus Reed, he's a park ranger with worsening neuropsychiatric symptoms",
        "description": "Zombie demo: neuropsych progression → Solanum encephalopathy",
        "expect_patient": True,
        "expect_min_turns": 2,
        "expect_keywords": ["neuro", "CSF"],
    },
    {
        "id": "zombie_labs",
        "message": "Can you review Marcus Reed's lab results? His symptoms have been escalating.",
        "description": "Zombie labs — should find CSF abnormalities, EEG",
        "expect_patient": True,
        "expect_min_turns": 1,
        "expect_keywords": ["CSF"],
    },
    {
        "id": "zombie_full",
        "message": "I need a complete clinical assessment of Marcus Reed. He was initially diagnosed with depression but symptoms keep getting worse.",
        "description": "Zombie full workup — should discover CDC advisory, novel pathogen",
        "expect_patient": True,
        "expect_min_turns": 3,
        "expect_keywords": ["encephalopathy"],
    },
]

MODELS = ["claude", "gpt4", "gemini"]


def run_query(host, message, model, timeout=180):
    """Send a query to the server and collect all SSE events."""
    url = f"http://{host}/api/query"
    data = json.dumps({"message": message, "model": model}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    events = []
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            buffer = ""
            for line in resp:
                line = line.decode("utf-8")
                buffer += line
                if line == "\n" and buffer.strip():
                    # Parse SSE event
                    event_type = None
                    event_data = None
                    for part in buffer.strip().split("\n"):
                        if part.startswith("event: "):
                            event_type = part[7:]
                        elif part.startswith("data: "):
                            try:
                                event_data = json.loads(part[6:])
                            except json.JSONDecodeError:
                                event_data = {"raw": part[6:]}
                    if event_type and event_data:
                        events.append({"type": event_type, "data": event_data})
                    buffer = ""
    except urllib.error.URLError as e:
        return {"error": str(e), "events": events, "elapsed": time.time() - start}
    except Exception as e:
        return {"error": str(e), "events": events, "elapsed": time.time() - start}

    elapsed = time.time() - start
    return {"error": None, "events": events, "elapsed": elapsed}


def analyze_result(result, prompt_config):
    """Analyze a pipeline result for quality indicators."""
    analysis = {
        "success": result["error"] is None,
        "error": result["error"],
        "elapsed_s": round(result["elapsed"], 1),
        "event_count": len(result["events"]),
    }

    if not analysis["success"]:
        return analysis

    # Extract key data
    events = result["events"]
    event_types = [e["type"] for e in events]

    # Check de-identification
    deident = next((e["data"] for e in events if e["type"] == "deidentified_query"), None)
    if deident:
        analysis["phi_detected"] = bool(deident.get("token_summary"))
        analysis["token_summary"] = deident.get("token_summary", {})
    else:
        analysis["phi_detected"] = False

    # Count gatekeeper turns
    gk_queries = [e for e in events if e["type"] == "gatekeeper_query"]
    analysis["gatekeeper_turns"] = len(gk_queries)

    # Check graph traversal
    traversals = [e for e in events if e["type"] == "graph_traversal"]
    total_nodes = set()
    for t in traversals:
        total_nodes.update(t["data"].get("nodes", []))
    analysis["graph_nodes_accessed"] = len(total_nodes)

    # Check final response
    final = next((e["data"] for e in events if e["type"] == "final_response"), None)
    if final:
        analysis["has_final_response"] = True
        analysis["citation_count"] = len(final.get("citations", []))
        analysis["response_length"] = len(final.get("content", ""))

        content_lower = final.get("content", "").lower()

        # Check expected keywords
        found_keywords = []
        missing_keywords = []
        for kw in prompt_config.get("expect_keywords", []):
            if kw.lower() in content_lower:
                found_keywords.append(kw)
            else:
                missing_keywords.append(kw)
        analysis["found_keywords"] = found_keywords
        analysis["missing_keywords"] = missing_keywords

        # Check for real name rehydration
        analysis["name_rehydrated"] = "john smith" in content_lower

        # Snippet
        analysis["response_snippet"] = final.get("content", "")[:300]
    else:
        analysis["has_final_response"] = False

    # Check for errors in events
    errors = [e for e in events if e["type"] == "error"]
    analysis["pipeline_errors"] = [e["data"].get("content", "") for e in errors]

    # Quality checks
    issues = []
    if prompt_config.get("expect_patient") and not analysis.get("phi_detected"):
        issues.append("PHI NOT DETECTED — patient name not redacted")
    if analysis.get("gatekeeper_turns", 0) < prompt_config.get("expect_min_turns", 1):
        issues.append(f"Too few gatekeeper turns ({analysis.get('gatekeeper_turns', 0)} < {prompt_config.get('expect_min_turns', 1)})")
    if analysis.get("graph_nodes_accessed", 0) == 0:
        issues.append("No graph nodes accessed — patient lookup may have failed")
    if not analysis.get("has_final_response"):
        issues.append("No final_response event received")
    if analysis.get("missing_keywords"):
        issues.append(f"Missing expected keywords: {analysis['missing_keywords']}")
    if analysis.get("pipeline_errors"):
        issues.append(f"Pipeline errors: {analysis['pipeline_errors']}")

    analysis["issues"] = issues
    analysis["grade"] = "PASS" if not issues else "WARN" if len(issues) <= 1 else "FAIL"

    return analysis


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1, help="Runs per model per prompt")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--models", nargs="+", default=MODELS)
    parser.add_argument("--prompts", nargs="+", default=None, help="Prompt IDs to test")
    args = parser.parse_args()

    prompts = DEMO_PROMPTS
    if args.prompts:
        prompts = [p for p in DEMO_PROMPTS if p["id"] in args.prompts]

    total = len(prompts) * len(args.models) * args.runs
    print(f"Running {total} tests: {len(prompts)} prompts x {len(args.models)} models x {args.runs} runs")
    print(f"Server: {args.host}")
    print("=" * 80)

    results = []

    for prompt_cfg in prompts:
        print(f"\n## {prompt_cfg['description']}")
        print(f"   Prompt: \"{prompt_cfg['message'][:80]}...\"")

        for model in args.models:
            for run in range(args.runs):
                label = f"   [{model}] run {run+1}/{args.runs}"
                sys.stdout.write(f"{label} ... ")
                sys.stdout.flush()

                result = run_query(args.host, prompt_cfg["message"], model)
                analysis = analyze_result(result, prompt_cfg)
                analysis["model"] = model
                analysis["prompt_id"] = prompt_cfg["id"]
                analysis["run"] = run + 1
                results.append(analysis)

                grade = analysis["grade"]
                icon = "✓" if grade == "PASS" else "⚠" if grade == "WARN" else "✗"
                turns = analysis.get("gatekeeper_turns", "?")
                citations = analysis.get("citation_count", "?")
                elapsed = analysis.get("elapsed_s", "?")
                nodes = analysis.get("graph_nodes_accessed", 0)

                print(f"{icon} {grade} | {elapsed}s | {turns} turns | {nodes} nodes | {citations} citations")

                if analysis.get("issues"):
                    for issue in analysis["issues"]:
                        print(f"      ⚠ {issue}")

                if analysis.get("response_snippet"):
                    snippet = analysis["response_snippet"][:150].replace("\n", " ")
                    print(f"      → {snippet}...")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for model in args.models:
        model_results = [r for r in results if r["model"] == model]
        passes = sum(1 for r in model_results if r["grade"] == "PASS")
        warns = sum(1 for r in model_results if r["grade"] == "WARN")
        fails = sum(1 for r in model_results if r["grade"] == "FAIL")
        avg_time = sum(r.get("elapsed_s", 0) for r in model_results) / max(len(model_results), 1)
        avg_turns = sum(r.get("gatekeeper_turns", 0) for r in model_results) / max(len(model_results), 1)
        avg_citations = sum(r.get("citation_count", 0) for r in model_results) / max(len(model_results), 1)

        print(f"\n{model.upper()}: {passes}✓ {warns}⚠ {fails}✗ | avg {avg_time:.1f}s | avg {avg_turns:.1f} turns | avg {avg_citations:.0f} citations")

        # Show all unique issues
        all_issues = set()
        for r in model_results:
            for issue in r.get("issues", []):
                all_issues.add(issue)
        if all_issues:
            for issue in all_issues:
                print(f"  ⚠ {issue}")


if __name__ == "__main__":
    main()
