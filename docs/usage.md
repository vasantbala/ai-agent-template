# Usage & API Reference

## Base URL

```
http://localhost:8000
```

---

## Authentication

When `AUTH__ENABLED=true`, all `/v1/` routes require one of:

**API key** (recommended for server-to-server):
```
X-API-Key: sk-agent-abc123
```

**JWT bearer token**:
```
Authorization: Bearer <token>
```

The `/health` endpoint is always unauthenticated.

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

Restrict which tools the agent may call:

```env
AGENT__ALLOWED_TOOLS='["read_file", "list_directory"]'
```
