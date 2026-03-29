# MedGate Backend — Known Issues

Audit performed 2026-03-29 after merging `backend/server` into `main`.

---

## Critical (demo-breaking)

### C1. OpenAI adapter `parse_tool_call` type mismatch
- **File:** `backend/adapters/openai_adapter.py:31-38`
- **Problem:** `parse_tool_call` checks `type == "function"` but `_response_to_dict` normalizes all tool calls to `type: "tool_use"`. In the server pipeline (`server.py:188`), blocks from the normalized response are passed to `parse_tool_call`, which never matches — GPT-4 tool loop is completely broken.
- **Fix:** `parse_tool_call` should also handle normalized `tool_use` blocks, or the server should use `raw_message` for OpenAI.

### C2. OpenAI multi-turn message format wrong
- **File:** `backend/adapters/openai_adapter.py:52-58`, `backend/server.py:226-228`
- **Problem:** `server.py:228` appends `{"role": "assistant", "content": response.get("content", [])}` — the normalized block format. But OpenAI requires its native assistant format with `.tool_calls`. The `_response_to_dict` method produces a `raw_message` field with the correct format, but `server.py` never uses it. The second OpenAI API call will 400.
- **Fix:** `send_tool_result` should append the `raw_message` instead of the normalized blocks, or handle the conversion internally.

### C3. Synchronous Ollama calls block the async event loop
- **File:** `backend/gatekeeper.py:241-257`, `backend/server.py:149,206`
- **Problem:** `gatekeeper._chat()` uses synchronous `httpx.post()` inside an async pipeline. This blocks the entire asyncio event loop for the duration of each Ollama call (1-5s each). During a multi-turn query, the server is completely unresponsive for 10-15s.
- **Fix:** Wrap sync calls with `asyncio.to_thread()` in `server.py`, or convert `_chat` to async with `httpx.AsyncClient`.

### C4. Family history queries always return empty
- **File:** `backend/gatekeeper.py:288-291`
- **Problem:** `get_family_history()` returns `list[dict]` (not `list[Node]`). `_fetch_from_graph` detects this and returns `[]`. The cloud model is told "information not available" even when family history data exists.
- **Fix:** Convert family history dicts to a composable format, or handle them in `_compose_response`.

### C5. Gemini adapter drops tool interaction history
- **File:** `backend/adapters/gemini_adapter.py:93-101`
- **Problem:** `_to_gemini_messages` only handles `str` content (`isinstance(content, str)`). Tool-use assistant messages and tool-result user messages have list/dict content — these are silently skipped. Multi-turn Gemini conversations lose all tool context.
- **Fix:** Handle non-string content types (tool_use blocks, tool_result blocks).

### C6. Unhandled Ollama errors crash the SSE stream
- **File:** `backend/gatekeeper.py:253-257`
- **Problem:** `_chat` doesn't catch `httpx.ConnectError`, `httpx.TimeoutException`, etc. If Ollama is down, the exception propagates up and crashes the SSE stream with no user-facing error event.
- **Fix:** Catch httpx transport errors in `_chat` or in the server pipeline.

---

## Moderate (degraded behavior)

### M1. NODE_CONFIG missing `family_history` and `disease_reference`
- **File:** `backend/server.py:56-64`
- **Problem:** Only 7 of 9 node types are configured. `family_history` (should be `#D946EF`, size 7) and `disease_reference` (should be `#3B82F6`, size 7) fall through to gray `#999`.
- **Fix:** Add the two missing entries to `NODE_CONFIG`.

### M2. Relative `GRAPH_PATH` and `PDF_DIR` break if CWD differs
- **File:** `backend/server.py:50-51`
- **Problem:** `GRAPH_PATH` defaults to `"data/stub/graph.json"` (relative). If the server is started from a different directory, the file won't be found. `stub_server.py` correctly uses `Path(__file__).parent.parent / "data"`.
- **Fix:** Use `Path(__file__)` to construct absolute defaults.

### M3. Partial patient names fail to resolve
- **File:** `backend/gatekeeper.py:109`, `backend/graph.py:137`
- **Problem:** `get_patient(kg, name="Smith")` does exact match. Users might say "Smith" instead of "John Smith" — the gatekeeper will fail to resolve the patient.
- **Fix:** Add substring/fuzzy matching to `get_patient`.

### M4. GraphPanel missing type display for `family_history` and `disease_reference`
- **File:** `frontend/src/components/GraphPanel.jsx:521-531`
- **Problem:** `getTypeDisplay` doesn't map these two types, showing raw strings instead of formatted names.
- **Fix:** Add mappings for both types.

### M5. System prompt code/doc mismatch
- **File:** `backend/adapters/base.py:25-28` vs `docs/backend.md:258-260`
- **Problem:** Code says "medication history + visit history"; docs say "family history + medication list". The cloud model requests different data depending on which you trust.
- **Fix:** Resolve the contradiction — align code with docs or vice versa.

### M6. Empty API key fallback gives confusing errors
- **File:** `backend/server.py:88-90`
- **Problem:** `os.getenv("ANTHROPIC_API_KEY", "")` passes empty string to the adapter. The API call then fails with a confusing 401 instead of a clear "API key not configured" error.
- **Fix:** Check for empty/missing keys before creating adapters.

### M7. Import inside loop body
- **File:** `backend/server.py:209`
- **Problem:** `from backend.graph import get_traversal_path` is inside the `while` loop. Works but wasteful.
- **Fix:** Move to top-level imports.

---

## Minor (doc drift / cleanup)

### L1. Dead `POST /api/switch-model` endpoint
- **File:** `backend/server.py:321-327`
- **Problem:** Frontend never calls it; model is passed per-query.

### L2. Vite port 5173 vs docs saying 3000
- **File:** `frontend/vite.config.js:8` vs `docs/interfaces.md`

### L3. Stub server loads production graph instead of stub
- **File:** `backend/stub_server.py:30`
- **Problem:** Points to `data/graph.json` instead of `data/stub/graph.json`.

### L4. `docs/backend.md` documents `/api/models` response as plain array
- **File:** `docs/backend.md:334`
- **Problem:** Code and `interfaces.md` return `{models: [...]}`. Doc is stale.

### L5. Gatekeeper accesses private attributes
- **File:** `backend/gatekeeper.py:265,167`
- **Problem:** Reaches into `TokenMapping._token_to_value` and `Graph._edges_from` directly.
