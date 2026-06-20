# Phase 8 Design — Demo UI

**Status:** DRAFT — awaiting user approval before any code is written  
**Goal:** A Gradio-based chat interface for showcasing and manually testing the agent. Runs as an optional sidecar — the core template is untouched.

---

## What Phase 8 Delivers

- **Chat tab** — real-time streaming chat against `/v1/agent/stream`; tokens appear as they arrive; session ID displayed so runs can be correlated in Langfuse
- **Knowledge base seeder tab** — paste documents into a text area and POST them to a thin seeder endpoint, or run the seed script directly; shows seeded document count
- **Config sidebar** — agent URL, tenant ID, user ID, and API key set via Gradio inputs; persisted in the browser session (no server-side state)
- **`docker-compose.demo.yml`** — overlay that adds the Gradio container alongside the existing `docker-compose.yml` services; main `docker-compose.yml` is not modified
- **Docs update** — examples updated to mention Gradio as an optional testing surface alongside curl/.NET

---

## What We're NOT Building

- User management or persistent login — the sidebar API key is sufficient for demos
- A production-grade frontend — Gradio is a dev/demo tool only
- Eval result visualisation — Langfuse covers this
- A mobile-responsive layout — desktop demo use only

---

## Directory Layout

```
demo/
  app.py              # Gradio application — single entrypoint
  requirements.txt    # gradio, httpx, sseclient-py — isolated from main project
  Dockerfile          # minimal Python image, runs app.py
  .env.example        # AGENT_URL, AGENT_API_KEY defaults for docker-compose
docker-compose.demo.yml   # overlay: adds `demo` service
```

The `demo/` directory is self-contained. Nothing in `src/` or `tests/` is touched.

---

## UI Layout

```
┌─────────────────────────────────────────────────────────────┐
│  AI Agent Demo                                              │
│                                                             │
│  ┌──────────────────┐  ┌─────────────────────────────────┐ │
│  │ Config           │  │ Chat          │ KB Seeder        │ │
│  │                  │  │               │                  │ │
│  │ Agent URL        │  │ ┌───────────┐ │                  │ │
│  │ [localhost:8000] │  │ │ assistant │ │ Documents        │ │
│  │                  │  │ │ Hello!... │ │ [text area]      │ │
│  │ Tenant ID        │  │ └───────────┘ │                  │ │
│  │ [local-dev     ] │  │ ┌───────────┐ │ [Seed KB]        │ │
│  │                  │  │ │ user      │ │                  │ │
│  │ User ID          │  │ │ What is..│ │ Seeded: 0 docs   │ │
│  │ [optional      ] │  │ └───────────┘ │                  │ │
│  │                  │  │               │                  │ │
│  │ API Key          │  │ [Type here ]  │                  │ │
│  │ [••••••••••••  ] │  │ [Send]        │                  │ │
│  │                  │  │               │                  │ │
│  │ Session ID       │  │ Session:      │                  │ │
│  │ [auto-generated] │  │ 3f2e1d...     │                  │ │
│  └──────────────────┘  └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Designs

### `demo/app.py`

Single file. Three logical sections:

**1. Config sidebar**

Gradio `gr.Sidebar` with:
- `agent_url` — text input, default `http://localhost:8000`
- `tenant_id` — text input, default `local-dev`
- `user_id` — text input, optional
- `api_key` — password input, optional (maps to `X-API-Key` header)
- `session_id` — read-only display, regenerated on "New session" button

**2. Chat tab**

`gr.ChatInterface` backed by a streaming generator function:

```python
import httpx, json

def chat(message, history, agent_url, tenant_id, user_id, api_key, session_id):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    body = {
        "tenant_id": tenant_id,
        "session_id": session_id,
        "user_id": user_id or None,
        "input": message,
    }

    partial = ""
    with httpx.Client(timeout=120) as client:
        with client.stream("POST", f"{agent_url}/v1/agent/stream",
                           headers=headers, json=body) as resp:
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    if event.get("type") == "token":
                        partial += event["content"]
                        yield partial
```

Uses Gradio's generator-based streaming — `yield partial` updates the response in real time.

**3. KB Seeder tab**

- `gr.Textbox(lines=15)` — paste documents (one per line)
- `gr.Button("Seed KB")` — POSTs each line to the agent's seeder endpoint (see below)
- `gr.Markdown` — shows count of seeded documents and any errors

The seeder calls a thin `/v1/kb/seed` endpoint added to the agent API (see below).

---

### Seeder endpoint (`src/api/routes/kb.py`)

One new route added to the main app:

```
POST /v1/kb/seed
{
  "tenant_id": "acme",
  "documents": ["Doc 1 text", "Doc 2 text", ...]
}

Response 200:
{"seeded": 3}
```

Internally calls `MemoryStore.store()` for each document. Only active when `MEMORY__ENABLED=true`; returns 400 otherwise.

This endpoint is also useful outside the demo — curl, .NET, or CI pipelines can use it to programmatically seed the KB.

---

### `demo/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app.py .
EXPOSE 7860
CMD ["python", "app.py"]
```

### `demo/requirements.txt`

```
gradio>=4.0
httpx>=0.27
sseclient-py>=1.8
```

### `docker-compose.demo.yml`

```yaml
# Run alongside docker-compose.yml:
#   docker compose -f docker-compose.yml -f docker-compose.demo.yml up
services:
  demo:
    build: ./demo
    ports:
      - "7860:7860"
    environment:
      - AGENT_URL=http://agent:8000
      - AGENT_API_KEY=${AGENT_API_KEY:-}
    depends_on:
      - agent
```

The `agent` service must be defined in the base `docker-compose.yml` (the agent container already built from `Dockerfile`). If running the agent locally without Docker, set `AGENT_URL=http://host.docker.internal:8000`.

---

## Docs Updates

### `docs/examples/single-agent-kb-qa.md`

Add a section **"Testing with the Gradio demo UI"** after the curl/streaming section:

```markdown
### Gradio demo UI (optional)

If you prefer a chat interface over curl, run the demo UI alongside the agent:

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml up
```

Then open http://localhost:7860. Set the tenant ID to `acme` and start chatting.
The KB Seeder tab lets you paste documents directly into Qdrant without running
the seed script.
```

### `docs/examples/multi-agent-research.md`

Add a note under the Querying section:

```markdown
### Gradio demo UI (optional)

```bash
docker compose -f docker-compose.yml \
               -f docker-compose.research.yml \
               -f docker-compose.demo.yml up
```

Point the Config sidebar at `http://localhost:8000` (the parent agent).
The researcher sub-agent is called internally — you only interact with the parent.
```

---

## Build Order

| # | Component | Files |
|---|---|---|
| 1 | Seeder endpoint | `src/api/routes/kb.py`, `src/api/main.py` + tests |
| 2 | Gradio app | `demo/app.py`, `demo/requirements.txt`, `demo/Dockerfile`, `demo/.env.example` |
| 3 | Docker Compose overlay | `docker-compose.demo.yml` |
| 4 | Docs updates | `docs/examples/single-agent-kb-qa.md`, `docs/examples/multi-agent-research.md` |

---

## Definition of Done for Phase 8

- [ ] `POST /v1/kb/seed` seeds documents into Qdrant and returns count; returns 400 when memory disabled
- [ ] `docker compose -f docker-compose.yml -f docker-compose.demo.yml up` starts Gradio on `:7860`
- [ ] Chat tab streams tokens in real time from `/v1/agent/stream`
- [ ] KB Seeder tab seeds documents and shows confirmation
- [ ] Config sidebar API key is sent as `X-API-Key` when set
- [ ] Session ID is displayed in the sidebar and sent on every message
- [ ] Examples docs mention `docker-compose.demo.yml` as the optional testing path
- [ ] Core `docker-compose.yml` is unchanged
