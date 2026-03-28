# MedGate — Backend Technical Spec

**Parent:** [TECHNICAL.md](../TECHNICAL.md) §2
**Owner:** Backend developer(s)
**Last updated:** 2026-03-28

This document covers the GX10 backend server, the gatekeeper model, the token mapping system, and cloud model integration. For product requirements, see [PRD.md](../PRD.md).

---

## 1. GX10 Hardware Context

The ASUS Ascent GX10 is powered by the **NVIDIA GB10 Grace Blackwell Superchip** — a fused CPU+GPU package, not a low-power NPU:

- **GPU:** NVIDIA Blackwell — 6,144 CUDA cores, 5th-gen Tensor Cores
- **CPU:** 20-core ARM v9.2-A Grace CPU (10x Cortex-X925 + 10x Cortex-A725)
- **AI compute:** Up to **1 petaFLOP (1,000 TOPS)** at FP4 precision
- **Memory:** 128GB unified LPDDR5x at 273 GB/s (shared between CPU and GPU, like Apple Silicon)
- **Interconnect:** NVLink C2C at 600 GB/s bidirectional between CPU and GPU

Nearly all 128GB is available for model loading. The memory bandwidth (273 GB/s) is the primary bottleneck for LLM inference — it determines tokens/sec for autoregressive decoding.

---

## 2. Gatekeeper Model

### 2.1 Model Selection

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

### 2.2 Inference Setup

The gatekeeper model runs via a local inference server on the GX10. Options:
- **Ollama** — simplest setup, good for hackathon, supports quantized models, CUDA-accelerated on GB10
- **llama.cpp server** — more control, supports NVIDIA-specific quantization formats (MXFP4), slightly better performance
- **vLLM** — best throughput, native Blackwell support, but heavier setup

**Hackathon recommendation:** Ollama for simplicity. It can be set up in minutes, supports all candidate models, runs natively on the Blackwell GPU via CUDA, and exposes a simple HTTP API that the GX10 backend can call. If we need MXFP4 quantization for better speed, switch to llama.cpp server.

The gatekeeper runs as a persistent process. It does NOT cold-start per query — the model is loaded once and stays in memory. At the 27B Q4 level, the model occupies ~18-20GB of the 128GB unified memory, leaving >100GB for the knowledge graph, token mappings, and OS.

### 2.3 Gatekeeper System Prompt

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

### 2.4 Gatekeeper Functions

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

## 3. Token Mapping System

### 3.1 Token Format

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

### 3.2 Mapping Lifecycle

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

### 3.3 Token Generation

Tokens are generated by deterministic code, NOT by the LLM. The code:
1. Receives PHI spans identified by the gatekeeper model (e.g., "John Smith" at position 14-24)
2. Assigns the next available token of the appropriate type
3. Stores the mapping in a Python dict (or JS object)
4. Performs string replacement in the query

This ensures tokens are always correctly formed, never duplicated, and the mapping is always consistent.

### 3.4 Dates — Special Handling

Exact dates are PHI under HIPAA Safe Harbor (year is allowed). The gatekeeper converts dates to relative descriptions:

- "January 15, 2026" → "approximately 2 months ago"
- "March 2024" → "approximately 2 years ago"
- "2019" → "2019" (year alone is allowed)

This conversion happens at the gatekeeper level before the sanitized query reaches the cloud. The relative description preserves temporal reasoning capability for the cloud model while removing the identifier.

---

## 4. Cloud Model Integration

### 4.1 Multi-Provider Adapter

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

### 4.2 Cloud Model System Prompt

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

### 4.3 Tool Definition

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

## 5. GX10 Backend Server

### 5.1 Tech Stack

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

### 5.2 API Endpoints

```
POST /api/query
  Body: { message: string, model: "claude" | "gpt4" | "gemini" }
  Response: WebSocket/SSE stream of events (see frontend spec section 3)

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

### 5.3 Query Processing Pipeline (Pseudocode)

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

## 6. File Structure (Backend)

```
backend/
├── server.py                   # FastAPI main server
├── gatekeeper.py               # Gatekeeper logic (PHI detection, graph query, redaction)
├── token_manager.py            # Ephemeral token mapping lifecycle
├── graph.py                    # Knowledge graph loading and traversal
├── adapters/
│   ├── base.py                 # Abstract cloud adapter
│   ├── claude_adapter.py       # Anthropic API
│   ├── openai_adapter.py       # OpenAI API
│   └── gemini_adapter.py       # Google GenAI API
├── citation.py                 # REF token management and re-hydration
└── requirements.txt
```
