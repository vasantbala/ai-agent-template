# Example: Knowledge Base Q&A

A single agent that answers questions from a document collection stored in Qdrant. The agent retrieves the most relevant chunks via embedding similarity before each LLM call, so answers are grounded in your content rather than the model's training data.

**What this demonstrates:**
- Qdrant vector memory (Phase 3)
- `MEMORY__SCOPE=tenant` — all documents shared across a tenant
- Seeding the knowledge base via the Python API
- Querying via `/v1/agent/run` and `/v1/agent/stream`

---

## Architecture

```
Client (curl / .NET)
    │
    ▼
POST /v1/agent/run
    │
    ▼
retrieve_memories node  ←── Qdrant (embedded docs)
    │
    ▼
reason node (LLM)  — synthesises answer from retrieved context
    │
    ▼
Response
```

---

## Setup

### 1. Start services

```bash
docker compose up -d   # starts Qdrant on :6333 and Langfuse on :3000
```

### 2. Configure `.env`

```env
TENANT_ID=local-dev
LLM__PROVIDER=anthropic
LLM__MODEL=claude-sonnet-4-6
LLM__API_KEY=sk-ant-...

LANGFUSE__PUBLIC_KEY=pk-lf-...
LANGFUSE__SECRET_KEY=sk-lf-...
LANGFUSE__HOST=http://localhost:3000

# Enable vector memory
MEMORY__ENABLED=true
MEMORY__SCOPE=tenant        # all sessions share the same knowledge base
MEMORY__TOP_K=5             # retrieve 5 chunks per query
MEMORY__QDRANT_URL=http://localhost:6333

EMBEDDING__MODEL=text-embedding-3-small
EMBEDDING__API_KEY=sk-...   # or leave unset to fall back to LLM__API_KEY
```

### 3. Seed the knowledge base

Create a seed script `scripts/seed_kb.py`:

```python
import asyncio
from config.settings import get_settings
from memory.embedding import EmbeddingClient
from memory.store import MemoryStore, Memory

# Your documents — replace with real content or load from files
DOCUMENTS = [
    "Enterprise licenses support up to 50 seats and include 24/7 priority support and a dedicated customer success manager.",
    "Standard licenses support up to 5 seats. Upgrades to Enterprise are available at any time with prorated pricing.",
    "All annual plans include a 30-day money-back guarantee. Monthly plans can be cancelled at any time with no refund.",
    "The REST API is available on Enterprise plans only. Rate limits are 1000 requests/minute per tenant.",
    "Single sign-on (SSO) via SAML 2.0 is supported on Enterprise plans. Setup requires a verified domain.",
    "Data residency options (EU, US, APAC) are available on Enterprise plans. Data is encrypted at rest and in transit.",
    "Support SLAs: Enterprise — 1 hour response for P1; Standard — 8 hours for P1; Community — best effort.",
    "The agent SDK supports Python 3.11+ and integrates via HTTP/REST, making it consumable from any language or platform.",
]

TENANT_ID = "acme"


async def seed():
    settings = get_settings()
    embedder = EmbeddingClient(settings.embedding, llm_api_key=settings.llm.api_key)
    store = MemoryStore(settings.memory, embedder)

    await store.ensure_collection(dimensions=settings.embedding.dimensions)

    for i, doc in enumerate(DOCUMENTS):
        await store.store(Memory(
            text=doc,
            tenant_id=TENANT_ID,
            session_id="seed",
        ))
        print(f"Seeded [{i + 1}/{len(DOCUMENTS)}]: {doc[:60]}...")

    print(f"\nDone — {len(DOCUMENTS)} documents stored in Qdrant under tenant '{TENANT_ID}'")


asyncio.run(seed())
```

Run it:

```bash
uv run python scripts/seed_kb.py
```

### 4. Start the agent

```bash
uv run uvicorn api.main:app --reload
```

---

## Querying

### curl

```bash
curl -X POST http://localhost:8000/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "acme",
    "input": "What is the return policy for annual plans?"
  }'
```

**Response**

```json
{
  "session_id": "b3c4d5e6-...",
  "tenant_id": "acme",
  "output": "Annual plans include a 30-day money-back guarantee. Monthly plans can be cancelled at any time, though no refund is issued for partial months.",
  "tool_calls": [],
  "cost_usd": 0.0009,
  "trace_id": "lf-..."
}
```

### Streaming (curl)

```bash
curl -X POST http://localhost:8000/v1/agent/stream \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "acme", "input": "What SSO options are available?"}' \
  --no-buffer
```

### From .NET (C#)

```csharp
var payload = new
{
    tenant_id = "acme",
    input = "Does the Enterprise plan include API access?"
};

using var http = new HttpClient();
var response = await http.PostAsJsonAsync("http://localhost:8000/v1/agent/run", payload);
var result = await response.Content.ReadFromJsonAsync<AgentResponse>();
Console.WriteLine(result?.Output);
```

---

## How retrieval works

Before the LLM reasons over the user's question, the `retrieve_memories` node:

1. Embeds the user's input using the configured embedding model
2. Queries Qdrant with `top_k` nearest-neighbour search filtered to the current `tenant_id`
3. Injects the retrieved chunks as additional context into the conversation

The LLM then has both the question and the relevant knowledge-base excerpts in its context window, producing grounded answers without hallucination.

---

## Extending the knowledge base

To add more documents at runtime (e.g. after a product update):

```python
await store.store(Memory(
    text="New pricing: the Starter plan is now $29/month for 2 seats.",
    tenant_id="acme",
    session_id="update-2026-06",
))
```

Subsequent queries immediately benefit from the new content — no reindexing step required.

---

## Tuning retrieval quality

| Setting | Effect |
|---|---|
| `MEMORY__TOP_K` | More chunks = richer context but longer prompts; 3–7 is typical |
| `EMBEDDING__MODEL` | `text-embedding-3-large` gives better recall at higher cost |
| `MEMORY__SCOPE` | `user` isolates each user's KB; `tenant` shares across all users |

---

## Observability

Open Langfuse at `http://localhost:3000`. Each run creates a trace showing:

- The retrieved memory chunks (as a pre-LLM span)
- The LLM call with full prompt and response
- `cost_usd` as a score
- The session ID linking multi-turn conversations
