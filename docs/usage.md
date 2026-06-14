# Usage & API Reference

## Base URL

```
http://localhost:8000
```

---

## Authentication

When `AUTH__ENABLED=true`, all `/v1/` routes require one of the two schemes below. The `/health` endpoint is always unauthenticated.

---

### API key (recommended for server-to-server)

**Configure keys in `.env`:**

```env
AUTH__ENABLED=true
AUTH__API_KEYS='["sk-agent-abc123", "sk-agent-def456"]'
```

Keys are arbitrary strings — generate them however you like (`uuidgen`, `openssl rand -hex 32`, etc.). Each entry in the list is independently valid.

**curl:**

```bash
curl -X POST http://localhost:8000/v1/agent/run \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-agent-abc123" \
  -d '{"tenant_id": "acme", "input": "What is the refund policy?"}'
```

**Python:**

```python
import httpx

response = httpx.post(
    "http://localhost:8000/v1/agent/run",
    headers={"X-API-Key": "sk-agent-abc123"},
    json={"tenant_id": "acme", "input": "What is the refund policy?"},
)
print(response.json()["output"])
```

**.NET (C#):**

```csharp
using var http = new HttpClient();
http.DefaultRequestHeaders.Add("X-API-Key", "sk-agent-abc123");

var response = await http.PostAsJsonAsync(
    "http://localhost:8000/v1/agent/run",
    new { tenant_id = "acme", input = "What is the refund policy?" }
);
var result = await response.Content.ReadFromJsonAsync<AgentResponse>();
Console.WriteLine(result?.Output);
```

---

### JWT bearer token (useful when callers already have a token)

**Configure in `.env`:**

```env
AUTH__ENABLED=true
AUTH__JWT_SECRET=change-me-in-production-use-32-chars-min
AUTH__JWT_ALGORITHM=HS256
```

**Generate a token** (one-off script or CI step):

```python
# scripts/generate_token.py
from jose import jwt
import datetime, os

secret = os.environ["AUTH__JWT_SECRET"]
payload = {
    "sub": "my-service",              # who is calling
    "tenant_id": "acme",
    "iat": datetime.datetime.now(datetime.UTC),
    "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30),
}
token = jwt.encode(payload, secret, algorithm="HS256")
print(token)
```

```bash
AUTH__JWT_SECRET=change-me uv run python scripts/generate_token.py
```

**curl:**

```bash
TOKEN="eyJhbGci..."

curl -X POST http://localhost:8000/v1/agent/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"tenant_id": "acme", "input": "What is the refund policy?"}'
```

**.NET (C#):**

```csharp
// token retrieved from your auth service or config
var token = configuration["AgentToken"];

using var http = new HttpClient();
http.DefaultRequestHeaders.Authorization =
    new AuthenticationHeaderValue("Bearer", token);

var response = await http.PostAsJsonAsync(
    "http://localhost:8000/v1/agent/run",
    new { tenant_id = "acme", input = "What is the refund policy?" }
);
```

**Missing or invalid credentials return:**

```json
HTTP 401
{"detail": "Invalid or missing credentials"}
```

---

### Using both schemes together

You can configure both simultaneously — the middleware accepts either. Useful when different callers use different auth mechanisms:

```env
AUTH__ENABLED=true
AUTH__API_KEYS='["sk-agent-abc123"]'
AUTH__JWT_SECRET=change-me-in-production
```

API key is checked first; if absent or invalid, JWT is tried. If both fail, 401 is returned.

---

## Endpoints

### `GET /health`

Liveness check. Returns 200 when the service is up.

```json
{"status": "ok"}
```

---

### `POST /v1/agent/run`

Synchronous agent run. Blocks until the agent produces a final answer.

**Request**

```json
{
  "tenant_id": "acme",
  "session_id": "optional-session-id",
  "user_id": "alice",
  "input": "Summarise the Q3 sales report"
}
```

| Field | Required | Description |
|---|---|---|
| `tenant_id` | Yes | Tenant identifier — scopes memory, logs, traces |
| `session_id` | No | Conversation ID — auto-generated UUID if omitted |
| `user_id` | No | User identifier for per-user memory scoping |
| `input` | Yes | The user's message or task |

**Response**

```json
{
  "session_id": "3f2e1d...",
  "tenant_id": "acme",
  "output": "The Q3 sales report shows revenue of $2.4M...",
  "tasks_completed": [
    {
      "id": "abc123",
      "description": "Call read_file",
      "tool_name": "read_file",
      "tool_args": {"path": "/reports/q3.txt"},
      "status": "completed",
      "result": "Q3 Revenue: $2.4M..."
    }
  ],
  "tool_calls": [
    {
      "tool_name": "read_file",
      "args": {"path": "/reports/q3.txt"},
      "result": "Q3 Revenue: $2.4M...",
      "success": true
    }
  ],
  "cost_usd": 0.0018,
  "trace_id": "lf-trace-xyz"
}
```

**Error responses**

| Status | Cause |
|---|---|
| `401` | Auth enabled and key/token missing or invalid |
| `422` | Missing required fields or guardrail violation on input |
| `500` | Unhandled agent error |

---

### `POST /v1/agent/stream`

Streaming agent run. Returns a `text/event-stream` response with token-level chunks as the LLM generates them.

**Request** — same body as `/v1/agent/run`.

**Response** (SSE)

```
data: {"type": "token", "content": "The"}
data: {"type": "token", "content": " Q3"}
data: {"type": "token", "content": " report"}
data: {"type": "done", "output": "The Q3 report shows..."}
data: [DONE]
```

**Consuming from .NET**

```csharp
using var client = new HttpClient();
client.DefaultRequestHeaders.Add("X-API-Key", "sk-agent-abc123");

var body = JsonSerializer.Serialize(new { tenant_id = "acme", input = "Summarise Q3" });
var content = new StringContent(body, Encoding.UTF8, "application/json");

using var response = await client.PostAsync("http://localhost:8000/v1/agent/stream", content);
using var stream = await response.Content.ReadAsStreamAsync();
using var reader = new StreamReader(stream);

while (!reader.EndOfStream)
{
    var line = await reader.ReadLineAsync();
    if (line?.StartsWith("data: ") == true)
    {
        var data = line["data: ".Length..];
        if (data == "[DONE]") break;
        Console.Write(JsonDocument.Parse(data).RootElement.GetProperty("content").GetString());
    }
}
```

---

### `POST /v1/triggers/webhook`

Fire-and-forget trigger. Accepts a payload, starts the agent in the background, and returns 202 immediately. Use this when the caller doesn't need to wait for the result (event-driven pipelines, scheduled notifications).

**Request**

```json
{
  "tenant_id": "acme",
  "input": "Run the nightly compliance check",
  "session_id": "optional-override",
  "user_id": "system"
}
```

**Response** `202 Accepted`

```json
{
  "accepted": true,
  "session_id": "wh-a1b2c3d4"
}
```

The agent run proceeds asynchronously. Correlate it in Langfuse using the returned `session_id`.

---

## Multi-tenant isolation

Every request carries a `tenant_id`. The template scopes:

- **Memory** — Qdrant queries filter by `tenant_id`; tenants never see each other's stored memories
- **Langfuse traces** — tagged with `tenant_id` for dashboard filtering
- **Audit log** — every event records `tenant_id`
- **Session IDs** — unique per tenant; no cross-tenant session bleed

---

## Prompt versioning

System prompts live in `prompts/{version}/system.md`. Set the active version with:

```env
AGENT__PROMPT_VERSION=v2
```

Use `scripts/compare_evals.py` to A/B compare two prompt versions against the golden dataset:

```bash
uv run python scripts/compare_evals.py --versions v1 v2
```

---

## Human-in-the-loop (HITL)

When `RELIABILITY__HITL_ENABLED=true`, the graph pauses before executing each tool call and waits for an interrupt to be resolved. Use the LangGraph checkpoint API to inspect the pending state and resume with approval.

---

## MCP tool configuration

Tools are provided by MCP servers declared in `MCP_SERVERS`:

```env
# Local stdio process
MCP_SERVERS='[{
  "name": "filesystem",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
}]'

# Remote HTTP server
MCP_SERVERS='[{
  "name": "my-server",
  "transport": "http",
  "url": "http://mcp-server:8080"
}]'
```

Each MCP server config supports:

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Logical name — used in tool permission lists |
| `transport` | Yes | `stdio` / `http` / `sse` |
| `command` | For `stdio` | Executable to launch (e.g. `npx`) |
| `args` | For `stdio` | Arguments to the command |
| `url` | For `http`/`sse` | URL of the remote MCP server |
| `env` | No | Extra environment variables passed to the process |

Restrict which tools the agent may call:

```env
AGENT__ALLOWED_TOOLS='["read_file", "list_directory"]'
```

If `AGENT__ALLOWED_TOOLS` is empty (the default), the agent may call any tool exposed by the connected MCP servers. Attempting to call a disallowed tool raises a `ToolPermissionError` and the agent returns an error for that tool call rather than crashing.

---

## Knowledge base seeding

### `POST /v1/kb/seed`

Stores text documents into Qdrant so the agent can retrieve them during reasoning. Requires `MEMORY__ENABLED=true`.

**Request**

```json
{
  "tenant_id": "acme",
  "documents": [
    "Enterprise licenses support up to 50 seats.",
    "All annual plans include a 30-day money-back guarantee."
  ],
  "session_id": "seed",
  "user_id": null
}
```

| Field | Required | Description |
|---|---|---|
| `tenant_id` | Yes | Tenant to store documents under — scopes retrieval |
| `documents` | Yes | Array of plain text strings to embed and store |
| `session_id` | No | Session scope for the stored memories (default: `"seed"`) |
| `user_id` | No | User scope — only needed for `MEMORY__SCOPE=user` |

**Response**

```json
{"seeded": 2}
```

**Error** — if memory is not enabled:

```json
HTTP 400
{"detail": "Memory is not enabled. Set MEMORY__ENABLED=true to use the KB seeder."}
```

**curl example**

```bash
curl -X POST http://localhost:8000/v1/kb/seed \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-agent-abc123" \
  -d '{
    "tenant_id": "acme",
    "documents": [
      "Enterprise licenses support up to 50 seats and include 24/7 priority support.",
      "Standard licenses support up to 5 seats. Upgrades are available at any time."
    ]
  }'
```

Documents are embedded immediately and available for the agent to retrieve on the next run. There is no re-indexing step.

---

## Reliability

### Token budget

Caps total token usage per run. When the limit is reached the agent stops and returns an error message rather than continuing.

```env
RELIABILITY__MAX_TOKENS_PER_RUN=50000
```

### MCP retry and circuit breaker

Failed MCP tool calls are retried with exponential backoff:

```env
RELIABILITY__MCP_RETRY_ATTEMPTS=3
RELIABILITY__MCP_RETRY_BASE_DELAY=1.0    # delay doubles each attempt: 1s, 2s, 4s
```

After `RELIABILITY__CIRCUIT_BREAKER_FAILURE_THRESHOLD` consecutive failures the circuit opens and all further calls to that MCP server immediately return an error (no waiting). The circuit resets after `RELIABILITY__CIRCUIT_BREAKER_RESET_TIMEOUT` seconds.

```env
RELIABILITY__CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
RELIABILITY__CIRCUIT_BREAKER_RESET_TIMEOUT=60.0
```

### Context window management

When the conversation history exceeds the threshold (in tokens), the agent automatically summarises older turns to keep the active context within the LLM's window:

```env
RELIABILITY__CONTEXT_WINDOW_THRESHOLD=6000
```

### Human-in-the-loop (HITL)

```env
RELIABILITY__HITL_ENABLED=true
```

With HITL enabled, the graph pauses at an interrupt point before executing each tool call. The pending state is saved to the SQLite checkpoint store. Resume it by resolving the interrupt via the LangGraph SDK or a custom approval UI.

---

## Memory and retrieval

### Memory scopes

`MEMORY__SCOPE` controls which stored memories are visible to the agent during a run:

| Scope | Retrieves from | Use case |
|---|---|---|
| `session` | Current session only | Ephemeral working context for one conversation |
| `user` | All sessions for the same `user_id` within the tenant | Personalised assistant that remembers the user across sessions |
| `tenant` | All documents for the same `tenant_id` | Shared knowledge base — all users in the tenant share the same pool |
| `global` | All stored memories regardless of tenant | Single-tenant or internal tooling deployments |

### Embedding configuration

```env
EMBEDDING__MODEL=text-embedding-3-small   # any model supported by LiteLLM
EMBEDDING__API_KEY=sk-...                 # omit to reuse LLM__API_KEY
EMBEDDING__DIMENSIONS=1536                # must match the chosen model
```

Common model/dimension pairs:

| Model | Dimensions |
|---|---|
| `text-embedding-3-small` | 1536 |
| `text-embedding-3-large` | 3072 |
| `text-embedding-ada-002` | 1536 |

`EMBEDDING__DIMENSIONS` must match the model. Mismatches cause Qdrant collection creation to fail.

---

## Cost tracking

When `COST__ENABLED=true` (the default), the agent calculates `cost_usd` for each run using LiteLLM's pricing tables and returns it in the response. The value is also logged as a Langfuse score for dashboard filtering.

```env
COST__ENABLED=true
```

Cost appears in every `/v1/agent/run` response:

```json
{"cost_usd": 0.0018, ...}
```

For unknown or custom models where LiteLLM lacks pricing data, `cost_usd` is `0.0` rather than erroring. Disable cost tracking entirely with `COST__ENABLED=false`.

---

## Scheduled runs

The agent can be triggered on a cron schedule without an external job scheduler.

```env
SCHEDULE__ENABLED=true
SCHEDULE__CRON="0 9 * * *"          # every day at 09:00 UTC
SCHEDULE__INPUT="Run the daily digest report"
SCHEDULE__TENANT_ID=acme
SCHEDULE__SESSION_ID_PREFIX=scheduled  # session IDs will be scheduled-{uuid}
```

The scheduler starts when the FastAPI app starts (via a lifespan hook). Each scheduled run calls the same agentic loop as `/v1/agent/run`. Traces appear in Langfuse tagged with the `SCHEDULE__TENANT_ID` and a `session_id` prefixed by `SCHEDULE__SESSION_ID_PREFIX`.

**Cron syntax:** standard 5-field cron (`minute hour day month weekday`). Examples:

| Expression | Meaning |
|---|---|
| `0 9 * * *` | Daily at 09:00 UTC |
| `0 */6 * * *` | Every 6 hours |
| `0 9 * * 1` | Every Monday at 09:00 |
| `*/30 * * * *` | Every 30 minutes |

---

## Evals

The eval harness measures answer quality using an LLM-as-judge and a golden dataset of expected answers.

```env
EVAL__ENABLED=true
EVAL__METRICS='["correctness", "faithfulness"]'
EVAL__THRESHOLD=0.7
EVAL__MODEL=gpt-4o
EVAL__GOLDEN_DATASET_PATH=evals/golden/default.json
```

**Metrics:**

| Metric | What it measures |
|---|---|
| `correctness` | Does the agent's answer match the expected output semantically? |
| `faithfulness` | Is the answer grounded in the retrieved context (no hallucination)? |
| `relevancy` | Is the answer on-topic relative to the question? |

**Golden dataset format** (`evals/golden/default.json`):

```json
[
  {
    "id": "refund-policy",
    "input": "What is the return policy?",
    "expected_output": "Annual plans include a 30-day money-back guarantee.",
    "context": "All annual plans include a 30-day money-back guarantee."
  }
]
```

**Run the eval suite:**

```bash
uv run pytest tests/evals/ -m eval -v
```

**A/B compare two prompt versions:**

```bash
uv run python scripts/compare_evals.py --versions v1 v2
```

Scores are written to Langfuse as named scores (`correctness`, `faithfulness`) on each trace.

---

## Observability (Langfuse)

Every agent run automatically creates a Langfuse trace. Access the dashboard at the `LANGFUSE__HOST` you configured (default: `http://localhost:3000` when using Docker Compose).

**What each trace shows:**

| Span | Content |
|---|---|
| Root trace | Full input, final output, `cost_usd` score, duration |
| `retrieve_memories` | Retrieved chunks with similarity scores |
| `reason` | Full LLM prompt + response, token counts |
| `execute` | Tool name, arguments, result |

**Filtering tips:**

- Filter by `tenant_id` metadata to isolate a single tenant's traces
- Filter by `session_id` to follow a multi-turn conversation
- Use the Scores view to track `correctness` and `cost_usd` trends over time

**Langfuse configuration:**

```env
LANGFUSE__PUBLIC_KEY=pk-lf-...
LANGFUSE__SECRET_KEY=sk-lf-...
LANGFUSE__HOST=http://localhost:3000    # or https://cloud.langfuse.com for the hosted version
```

The `LANGFUSE__HOST` for the self-hosted Docker Compose version should point to `http://localhost:3000` (or `http://langfuse:3000` when connecting from another container).

---

## Demo UI

A Gradio interface for testing the agent interactively. Runs as a Docker Compose overlay — the core `docker-compose.yml` is unchanged.

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml up --build
```

Open **http://localhost:7860**.

**Features:**
- Chat tab — streams tokens in real time as the LLM generates them
- KB Seeder tab — paste documents and click Seed to store them in Qdrant via `POST /v1/kb/seed`
- Config sidebar — change Agent URL, Tenant ID, and API Key at runtime without restarting

**Pass an API key** (when `AUTH__ENABLED=true` on the agent):

```bash
AGENT_API_KEY=sk-agent-abc123 docker compose \
  -f docker-compose.yml -f docker-compose.demo.yml up --build
```

The demo container has its own `demo/.env.example`:

```env
AGENT_URL=http://localhost:8000   # or http://agent:8000 inside Docker
AGENT_API_KEY=                    # optional
```

> The demo UI is for development and manual testing only. It is not part of the production Docker Compose.

---

## Troubleshooting

**`401 Invalid or missing credentials`**
: `AUTH__ENABLED=true` but the request is missing `X-API-Key` or `Authorization: Bearer <token>`. Check that the key is in `AUTH__API_KEYS` or that the JWT is signed with `AUTH__JWT_SECRET`.

**`400 Memory is not enabled`** (on `/v1/kb/seed`)
: Set `MEMORY__ENABLED=true` in `.env` and restart the agent.

**`422 Input contains potential prompt injection`**
: The input guardrail blocked the request. Rephrase the input to avoid phrases that look like instruction override attempts.

**Cost is always `0.0`**
: The configured model is not in LiteLLM's pricing tables (common with custom or fine-tuned models). This is not an error — set `COST__ENABLED=false` to suppress the field.

**Qdrant collection errors on startup**
: `EMBEDDING__DIMENSIONS` does not match the model. Common mismatch: using `text-embedding-3-large` (3072 dims) with the default `EMBEDDING__DIMENSIONS=1536`. Update the env var and recreate the collection.

**Agent runs forever / exceeds iteration limit**
: Reduce `AGENT__MAX_ITERATIONS` or set `RELIABILITY__MAX_TOKENS_PER_RUN` to cap spend. The agent will return an error message instead of looping.

**Langfuse dashboard shows no traces**
: Verify `LANGFUSE__HOST` matches where Langfuse is running. When using Docker Compose, services connecting to Langfuse from inside a container should use `http://langfuse:3000`, not `http://localhost:3000`.
