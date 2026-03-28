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

## Git Conventions

This is a hackathon sprint — keep it simple:

- **Commit frequently.** Each meaningful unit of work gets its own commit immediately. Don't batch everything into one giant commit at the end.
- **Work on `main`** unless the user asks for a branch. No branching strategy needed for the hackathon.
- **Never force-push** without explicit approval.
- **Never push to remote** without explicit approval (unless the user has already asked you to push in the current request).
- **Commit messages:** Short, imperative, descriptive. E.g., "Add gatekeeper de-identification pipeline", "Fix token mapping lifecycle", "Wire up SSE streaming to frontend".
