"""Compare gatekeeper models on PHI detection accuracy and speed."""

import httpx
import json
import time

OLLAMA_URL = "http://localhost:11434"

SYSTEM_PROMPT = """You are the MedGate Gatekeeper. Identify ALL Protected Health Information (PHI) in the user query.

Return a JSON array of PHI spans. Each span has:
- "text": the exact PHI text
- "type": one of PATIENT, PROVIDER, FAMILY, MRN, DATE, LOCATION, CONTACT

Rules:
- Identify patient names, provider names, family member names, MRNs, SSNs, dates, locations, phone numbers, emails
- Do NOT flag clinical terms (conditions, symptoms, medications, lab values)
- Do NOT flag age, sex, or generic descriptions
- Return ONLY the JSON array"""

TESTS = [
    {
        "name": "Basic query",
        "query": "Tell me about John Smith, he has been having headaches for 3 months",
        "must_catch": ["John Smith"],
        "must_not_catch": ["headaches", "3 months"],
    },
    {
        "name": "Multiple PHI types",
        "query": "John Smith (MRN-78234) was seen by Dr. Sarah Chen at Springfield General Hospital on January 15, 2026. His wife Mary called from 555-0142.",
        "must_catch": ["John Smith", "MRN-78234", "Dr. Sarah Chen", "Springfield General Hospital", "Mary", "555-0142"],
        "must_not_catch": ["wife"],
    },
    {
        "name": "Clinical terms should NOT be redacted",
        "query": "The patient has systemic lupus erythematosus with ANA titer 1:320, WBC 3.2, prescribed hydroxychloroquine 200mg twice daily",
        "must_catch": [],
        "must_not_catch": ["systemic lupus", "ANA", "WBC", "hydroxychloroquine", "200mg", "1:320"],
    },
    {
        "name": "Tricky mixed query",
        "query": "Maria Garcia, 58 year old female from 480 George Street, was referred by Dr. James Wilson for uncontrolled diabetes. Her son Tom Garcia (emergency contact: 555-0198) should be notified.",
        "must_catch": ["Maria Garcia", "480 George Street", "Dr. James Wilson", "Tom Garcia", "555-0198"],
        "must_not_catch": ["58 year old", "female", "diabetes"],
    },
]

MODELS = ["mistral-small:24b", "qwen2.5:32b", "gemma2:27b"]


def extract_json_array(text):
    """Extract a JSON array from LLM output that may have extra text."""
    text = text.strip()
    # Remove markdown fences
    if "```" in text:
        lines = text.split("\n")
        cleaned = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                cleaned.append(line)
        text = "\n".join(cleaned)

    # Find the JSON array
    for i, c in enumerate(text):
        if c == "[":
            depth = 0
            for j in range(i, len(text)):
                if text[j] == "[":
                    depth += 1
                elif text[j] == "]":
                    depth -= 1
                if depth == 0:
                    return text[i : j + 1]
    return "[]"


def run_test(model, test):
    start = time.time()
    r = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": test["query"]},
            ],
            "stream": False,
            "options": {"temperature": 0.1},
        },
        timeout=120.0,
    )
    elapsed = time.time() - start

    data = r.json()
    content = data["message"]["content"]
    eval_count = data.get("eval_count", 0)
    eval_duration = data.get("eval_duration", 1) / 1e9
    tok_s = eval_count / eval_duration if eval_duration > 0 else 0

    try:
        spans = json.loads(extract_json_array(content))
    except json.JSONDecodeError:
        spans = []

    found_texts = [s.get("text", "") for s in spans]

    # Score: did it catch what it should?
    caught = 0
    missed = []
    for must in test["must_catch"]:
        if any(must.lower() in f.lower() for f in found_texts):
            caught += 1
        else:
            missed.append(must)

    # Score: did it wrongly flag clinical terms?
    false_positives = []
    for must_not in test["must_not_catch"]:
        if any(must_not.lower() in f.lower() for f in found_texts):
            false_positives.append(must_not)

    return {
        "caught": caught,
        "total_must": len(test["must_catch"]),
        "missed": missed,
        "false_positives": false_positives,
        "tok_s": tok_s,
        "elapsed": elapsed,
        "found": found_texts,
    }


if __name__ == "__main__":
    for model in MODELS:
        print(f"\n{'=' * 60}")
        print(f"MODEL: {model}")
        print(f"{'=' * 60}")

        total_caught = 0
        total_must = 0
        total_fp = 0
        speeds = []

        for test in TESTS:
            r = run_test(model, test)
            total_caught += r["caught"]
            total_must += r["total_must"]
            total_fp += len(r["false_positives"])
            speeds.append(r["tok_s"])

            status = "PASS" if not r["missed"] and not r["false_positives"] else "ISSUES"
            print(f"  [{status}] {test['name']} ({r['elapsed']:.1f}s, {r['tok_s']:.1f} tok/s)")
            if r["missed"]:
                print(f"         MISSED: {r['missed']}")
            if r["false_positives"]:
                print(f"         FALSE POS: {r['false_positives']}")

        avg_speed = sum(speeds) / len(speeds)
        recall = (total_caught / total_must * 100) if total_must > 0 else 100
        print(f"  ---")
        print(f"  PHI Recall: {total_caught}/{total_must} ({recall:.0f}%)")
        print(f"  False Positives: {total_fp}")
        print(f"  Avg Speed: {avg_speed:.1f} tok/s")

    print(f"\n{'=' * 60}")
    print("DONE")
