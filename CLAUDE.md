# MedGate — Claude Code Guidelines

## Key Documents

| Document | Purpose | When to read |
|----------|---------|--------------|
| `PRD.md` | Product requirements — scope, goals, user stories, success metrics | Before implementing any feature; to check if something is in/out of scope |
| `TECHNICAL.md` | Technical architecture index — maps each system component to a focused spec in `docs/` | Before starting work on any component; to find the right spec doc |
| `docs/backend.md` | GX10 backend, gatekeeper model, token mapping, cloud model integration | When working on the Python backend, Ollama setup, API adapters, or the privacy pipeline |
| `docs/frontend.md` | Chat UI, 3D graph visualization, PDF viewer, citation rendering | When working on the React frontend or any browser-side code |
| `docs/knowledge-graph.md` | Graph schema, node/edge types, PHI tagging, mock data generation | When working on the knowledge graph, data generation scripts, or graph traversal |
| `docs/demo.md` | System architecture overview, demo reliability strategy, full file structure | When planning the demo flow, debugging latency, or onboarding a new team member |

---

## Document Sync Rules

### 1. Flag document-affecting changes

When a requirement, scope, or architecture decision changes during implementation:
- Stop and tell the user which documents are affected
- Ask: "Should I update [document(s)] to reflect this change?"
- Never silently absorb a change that contradicts or extends what's documented

### 2. Find affected documents via the index

Read `TECHNICAL.md` to identify which `docs/*.md` files cover the component you're changing. A single change often affects multiple docs (e.g., changing the SSE event format affects both `docs/backend.md` and `docs/frontend.md`). Check cross-references.

### 3. Stop on contradictions

If the code contradicts a document (e.g., code uses a different API format than what's specced, a feature exists that's listed as out-of-scope, or a documented feature is missing):
- **Stop and ask the user:** "I noticed the repo does X but docs/Y.md says Z. Should I update the doc to match the code, or is the code wrong?"
- Never silently resolve contradictions yourself

### 4. Escalate open questions

When you encounter an unresolved design decision during implementation:
1. Stop — don't decide yourself
2. Research the options (read related docs, explore tradeoffs)
3. Present the options to the user with your recommendation
4. Only proceed after the user decides

### 5. Post-change review

After major changes (new feature, refactor, dependency change, scope change):
- Review `PRD.md` and the relevant `docs/*.md` files
- If any are stale, tell the user: "The following docs may need updating: [list]. Want me to update them?"

### 6. How to apply updates

- Make surgical edits — only change the affected parts, don't rewrite unrelated sections
- Keep the existing structure and style of the document
- Update "Last updated" dates in affected files
- If a new doc is added, renamed, or removed, update the index in `TECHNICAL.md`

---

## GX10 Device Access

The GX10 is the on-premises hardware that runs the gatekeeper model and holds the knowledge graph. Connection credentials are in `.env` (gitignored).

### Connecting

```bash
sshpass -p "$GX10_PASSWORD" ssh -o StrictHostKeyChecking=no "$GX10_USER@$GX10_HOST"
```

`sshpass` is required because the device uses password auth and agents can't type into interactive prompts. Install with `brew install sshpass` if missing.

### Device details

| | |
|---|---|
| **Hostname** | `gx10-4428` |
| **OS** | Ubuntu (aarch64/ARM), kernel 6.17 with NVIDIA overlay |
| **GPU** | NVIDIA GB10 (Blackwell), CUDA 13.0 |
| **Memory** | ~119GB unified LPDDR5x (shared CPU/GPU — see note below) |
| **Disk** | ~916GB NVMe, ~793GB free |
| **Python** | 3.12.3 |
| **Project dir** | `/home/asus/yale-hacks` (has its own git repo + venv) |
| **Ollama** | Running as systemd service, port `11434` |

### Unified memory

The GB10 uses a unified memory architecture (like Apple Silicon) — the CPU and GPU share a single 119GB LPDDR5x pool. There is no separate VRAM. Implications:

- **`nvidia-smi` cannot report GPU memory usage** — it shows "Not Supported". Use `free -h` to check total system memory instead.
- **Everything shares the same pool:** the Ollama model, the knowledge graph, the Python server, and the OS all compete for the same 119GB. A 27B Q4 model uses ~18-20GB, leaving ~95GB+ for everything else — not a concern for this project.
- **No CPU→GPU memory copies** — model inference doesn't pay a transfer penalty, which is why the GB10 punches above its weight on tokens/sec.

### Common operations

```bash
# Run a command on the GX10 (one-liner pattern)
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" "command here"

# Check Ollama models
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" "ollama list"

# Check running models
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" "ollama ps"

# Pull a new model
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" "ollama pull qwen2.5:32b"

# Test Ollama inference
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" "curl -s localhost:11434/api/generate -d '{\"model\":\"llama3.1:70b\",\"prompt\":\"hello\",\"stream\":false}'"

# Check memory (nvidia-smi shows "Not Supported" for memory on unified arch — use free instead)
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" "free -h"

# Copy files to the device
sshpass -p "$GX10_PASSWORD" scp local_file "$GX10_USER@$GX10_HOST:/home/asus/yale-hacks/"

# Copy files from the device
sshpass -p "$GX10_PASSWORD" scp "$GX10_USER@$GX10_HOST:/home/asus/yale-hacks/file" ./
```

### Guardrails

- **Never reboot** the device without asking the user
- **Never remove Ollama models** already loaded — they take a long time to re-pull over the network
- **Never modify files outside** `/home/asus/yale-hacks/` on the device
- **Ask before long-running operations** that could tie up the GPU (e.g., running a large model pull or benchmark)
- **Never hardcode or echo credentials** — always read from `.env` at runtime

---

## Git Conventions

This is a hackathon sprint — keep it simple:

- **Commit frequently.** Each meaningful unit of work gets its own commit immediately. Don't batch everything into one giant commit at the end.
- **Work on `main`** unless the user asks for a branch. No branching strategy needed for the hackathon.
- **Never force-push** without explicit approval.
- **Never push to remote** without explicit approval (unless the user has already asked you to push in the current request).
- **Commit messages:** Short, imperative, descriptive. E.g., "Add gatekeeper de-identification pipeline", "Fix token mapping lifecycle", "Wire up SSE streaming to frontend".
