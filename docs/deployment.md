# MedGate — GX10 Deployment Guide

**Parent:** [TECHNICAL.md](../TECHNICAL.md)
**Owner:** Whole team
**Last updated:** 2026-03-29

Step-by-step instructions to deploy MedGate to the GX10 and run the demo. Assumes all branches have been merged into `main`.

---

## Prerequisites

- All branches merged into `main` and pushed to remote
- GX10 reachable via Tailscale (confirm with `ping <gx10-tailscale-ip>`)
- `.env` file with GX10 SSH credentials (`GX10_HOST`, `GX10_USER`, `GX10_PASSWORD`)
- Cloud API keys ready: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`
- Node.js installed on your MacBook (for building the frontend)

---

## Step 1: Build the frontend (on your MacBook)

```bash
cd frontend
npm install
npm run build
```

This produces `frontend/dist/` — static HTML/JS/CSS. This is the only step that needs Node.js. We do NOT install Node on the GX10.

---

## Step 2: Get the build onto the remote

The hashed JS/CSS bundles in `frontend/dist/` are gitignored, so a plain `git add` skips them. Force-add the build so the GX10 can pull it:

```bash
git add -f frontend/dist
git commit -m "Add frontend production build"
git push
```

If you'd rather not commit the bundle, `scp` it to the device instead (see Step 3) — either way `frontend/dist/` must exist on the GX10 before the server starts.

---

## Step 3: Pull on the GX10

```bash
# From your MacBook
source .env
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" \
  "cd /home/asus/yale-hacks && git pull"
```

If the GX10 repo has diverged or isn't set up yet, do a fresh clone instead:

```bash
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" \
  "cd /home/asus && git clone <repo-url> yale-hacks"
```

`data/pdfs/` is gitignored too, so a `git pull` or fresh clone brings no PDFs and citation clicks will 404. Copy the frontend build and the PDFs over directly:

```bash
sshpass -p "$GX10_PASSWORD" scp -r frontend/dist \
  "$GX10_USER@$GX10_HOST:/home/asus/yale-hacks/frontend/"
sshpass -p "$GX10_PASSWORD" scp -r data/pdfs \
  "$GX10_USER@$GX10_HOST:/home/asus/yale-hacks/data/"
```

If you have no local PDFs either, regenerate them first — see the README section on regenerating the clinical PDFs (`scripts/generate_documents.py`).

---

## Step 4: Create Python virtual environment (one-time)

```bash
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" \
  "cd /home/asus/yale-hacks && python3 -m venv .venv"
```

---

## Step 5: Install Python dependencies

```bash
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" \
  "cd /home/asus/yale-hacks && source .venv/bin/activate && pip install -r backend/requirements.txt"
```

If `backend/requirements.txt` doesn't exist yet, install manually:

```bash
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" \
  "cd /home/asus/yale-hacks && source .venv/bin/activate && \
   pip install fastapi uvicorn httpx anthropic openai google-generativeai"
```

---

## Step 6: Set up environment variables on GX10

Create `/home/asus/yale-hacks/.env` on the device:

```bash
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" "cat > /home/asus/yale-hacks/.env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AI...
GATEKEEPER_MODEL=mistral-small:24b
OLLAMA_URL=http://localhost:11434
EOF"
```

**Important:** Replace the placeholder API keys with real values. Never commit this file.

`GRAPH_PATH` and `PDF_DIR` are optional — they default to `data/graph.json` and `data/pdfs` under the repo root, resolved from the backend package location, so the server finds them no matter which directory it is started from. Set them only to point at data outside the repo.

---

## Step 7: Verify Ollama is running

```bash
# Check the service
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" "systemctl status ollama"

# Check the gatekeeper model is loaded
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" "ollama list"

# Quick inference test
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" \
  "curl -s localhost:11434/api/generate -d '{\"model\":\"mistral-small:24b\",\"prompt\":\"hello\",\"stream\":false}' | head -c 200"
```

If the gatekeeper model isn't pulled yet:

```bash
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" "ollama pull mistral-small:24b"
```

This takes a while (~15-20 min depending on network). Do it well before the demo.

---

## Step 8: Start the server

```bash
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" \
  "cd /home/asus/yale-hacks && source .venv/bin/activate && source .env && \
   uvicorn backend.server:app --host 0.0.0.0 --port 8000"
```

The server should log:
- Graph loaded (node/edge counts)
- Ollama reachable
- Listening on `0.0.0.0:8000`

To run in the background (so it survives SSH disconnect):

```bash
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" \
  "cd /home/asus/yale-hacks && source .venv/bin/activate && source .env && \
   nohup uvicorn backend.server:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &"
```

---

## Step 9: Smoke test

From your MacBook browser, open: `http://<gx10-tailscale-ip>:8000`

### API checks (curl from your MacBook)

```bash
GX10=<gx10-tailscale-ip>

# 1. Frontend loads
curl -s http://$GX10:8000/ | head -c 200

# 2. Graph endpoint returns data
curl -s http://$GX10:8000/api/graph | python3 -c "import sys,json; g=json.load(sys.stdin); print(f'{len(g[\"nodes\"])} nodes, {len(g[\"edges\"])} edges')"

# 3. Models endpoint
curl -s http://$GX10:8000/api/models

# 4. PDF serving (pick any existing PDF)
curl -sI http://$GX10:8000/api/pdf/intake_form_smith_2025_jun.pdf
```

### Full pipeline test

Open the UI in a browser, select Claude, and type:

> Tell me about John Smith, he's been having recurring headaches and joint pain

You should see:
1. RedactedView shows de-identified query with `[PATIENT_1]`
2. Graph nodes light up as the gatekeeper traverses
3. 2-4 gatekeeper turns (labs, family history, medications)
4. Final response with real names and clickable citations

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Connection refused` on port 8000 | Server not running | Check step 8, look at `server.log` |
| Frontend loads but API calls fail | CORS or static file mount missing | Check that `server.py` mounts `frontend/dist/` as static files |
| `deidentified_query` event never arrives | Ollama not reachable or model not loaded | Check step 7 |
| Gatekeeper responds but cloud model fails | API key missing or wrong | Check `.env` on GX10 |
| Graph shows 0 nodes | `GRAPH_PATH` wrong or file missing | Verify `data/graph.json` exists on GX10 |
| Very slow (>60s per turn) | Multiple models loaded in Ollama eating memory | Run `ollama ps` and unload extras |
| PDF citations return 404 | PDFs not copied (`data/pdfs/` is gitignored) or `PDF_DIR` points elsewhere | Verify `data/pdfs/` has files on GX10; copy or regenerate them (Step 3) |
| Frontend returns 404 / blank page | `frontend/dist/` missing (gitignored bundles) | Build locally and copy the directory over (Steps 1-3) |

---

## Quick redeploy (after code changes)

```bash
# On your MacBook — rebuild frontend if changed
cd frontend && npm run build

# Commit and push (-f on dist — its bundles are gitignored)
git add -A && git add -f frontend/dist && git commit -m "..." && git push

# Pull on GX10
source .env
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" \
  "cd /home/asus/yale-hacks && git pull"

# Restart server (kill old, start new)
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" \
  "pkill -f 'uvicorn backend.server' || true"
sshpass -p "$GX10_PASSWORD" ssh "$GX10_USER@$GX10_HOST" \
  "cd /home/asus/yale-hacks && source .venv/bin/activate && source .env && \
   nohup uvicorn backend.server:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &"
```

---

## Pre-demo checklist

- [ ] All branches merged into `main`
- [ ] Frontend built and `frontend/dist/` present on GX10 (force-committed or scp'd)
- [ ] `git pull` completed on GX10
- [ ] `.env` on GX10 has all 3 API keys
- [ ] Ollama running, gatekeeper model loaded (`ollama ps`)
- [ ] `data/graph.json` exists on GX10 (1,126 nodes, 1,721 edges)
- [ ] `data/pdfs/` has PDFs on GX10 — gitignored, so copy or regenerate them (at least Smith + Reed)
- [ ] Server starts without errors
- [ ] `http://<gx10-tailscale-ip>:8000` loads the frontend
- [ ] `/api/graph` returns full graph
- [ ] Full pipeline test with John Smith query succeeds
- [ ] Server-side logging shows pipeline stages with timing (see [backend.md §6](backend.md))
- [ ] Fallback screen recording prepared
- [ ] Team knows the demo patient scenario (John Smith — SLE differential)
