# Gatekeeper Model Speed Benchmark — 2026-03-28

**Device:** GX10 (gx10-4428), NVIDIA GB10 Blackwell, 119GB unified LPDDR5x
**Ollama version:** default install via snap
**Prompt:** "Explain in 2-3 sentences what HIPAA Safe Harbor de-identification means and list 3 of the 18 identifiers that must be removed."
**Runs:** 3 per model
**Note:** All 4 models were pulled simultaneously, so Ollama was swapping models in/out of memory between runs. Solo-loaded speeds will be higher (see "cold start" single-model results at the bottom).

## Results

| Model | Param | Quantization | Run 1 (tok/s) | Run 2 (tok/s) | Run 3 (tok/s) | Avg (tok/s) | Tokens generated |
|---|---|---|---|---|---|---|---|
| `mistral-small:24b` | 24B | Q4_K_M | 13.58 | 9.04 | 5.72 | **9.4** | 114, 195, 117 |
| `qwen2.5:32b` | 32B | Q4_K_M | 8.82 | 10.16 | 10.15 | **9.7** | 81, 81, 85 |
| `gemma2:27b` | 27B | Q4_K_M | 5.80 | 5.66 | 8.92 | **6.8** | 78, 84, 79 |
| `llama3.1:70b` | 70B | Q4_K_M | 4.61 | 4.77 | 4.72 | **4.7** | 82, 137, 111 |

## Single-model cold start (one model loaded, no contention)

Measured earlier in the session with a simple "hello" prompt, each model loaded solo:

| Model | tok/s |
|---|---|
| `mistral-small:24b` | 16.8 |
| `gemma2:27b` | 15.1 |
| `qwen2.5:32b` | 11.4 |

## Observations

- **Model swapping significantly affects throughput.** The multi-model benchmark shows 5-10 tok/s, but solo-loaded models hit 11-17 tok/s. In production, only one gatekeeper model will be loaded — expect the higher numbers.
- **Mistral Small is fastest** when loaded solo (16.8 tok/s), followed by Gemma 2 (15.1) and Qwen 2.5 (11.4).
- **LLaMA 3.1 70B is consistently ~4.7 tok/s** — too slow for demo use. A 200-token gatekeeper response would take ~42 seconds. Kept as a quality reference only.
- **Qwen 2.5 32B is most consistent** across runs even under contention (8.8–10.2 tok/s, tight spread).
- **All models correctly identified HIPAA Safe Harbor** and listed valid identifiers. Quality evaluation (PHI detection recall, format compliance) is a separate eval — this benchmark only measures speed.
- Docs have been updated to reflect these measured speeds (previously estimated at 30-50 tok/s).

## Raw data

### mistral-small:24b
- Run 1: 114 tokens, 8.40s eval, 13.58 tok/s, prompt_eval 195 tokens
- Run 2: 195 tokens, 21.57s eval, 9.04 tok/s, prompt_eval 195 tokens
- Run 3: 117 tokens, 20.46s eval, 5.72 tok/s, prompt_eval 195 tokens

### qwen2.5:32b
- Run 1: 81 tokens, 9.19s eval, 8.82 tok/s, prompt_eval 61 tokens
- Run 2: 81 tokens, 7.97s eval, 10.16 tok/s, prompt_eval 61 tokens
- Run 3: 85 tokens, 8.37s eval, 10.15 tok/s, prompt_eval 61 tokens

### gemma2:27b
- Run 1: 78 tokens, 13.45s eval, 5.80 tok/s, prompt_eval 39 tokens
- Run 2: 84 tokens, 14.85s eval, 5.66 tok/s, prompt_eval 39 tokens
- Run 3: 79 tokens, 8.85s eval, 8.92 tok/s, prompt_eval 39 tokens

### llama3.1:70b
- Run 1: 82 tokens, 17.80s eval, 4.61 tok/s, prompt_eval 41 tokens
- Run 2: 137 tokens, 28.70s eval, 4.77 tok/s, prompt_eval 41 tokens
- Run 3: 111 tokens, 23.53s eval, 4.72 tok/s, prompt_eval 41 tokens
