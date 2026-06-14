# AI Agent Template

A production-ready Python microservice template for building AI agents. Expose your agent over HTTP/REST so any host product — web, .NET, Windows Forms — can integrate without caring about the internal language.

Built on **LangGraph** + **LiteLLM** + **FastAPI**. Fork it, configure it, ship it.

---

## What's included

| Capability | Details |
|---|---|
| Agentic loop | LangGraph reason → execute → reason cycle with tool calling |
| LLM providers | OpenAI, Anthropic, OpenRouter — swap via config |
| MCP tools | Plug in any MCP server (filesystem, search, databases) |
| Memory | Long-term vector memory via Qdrant; scoped per session / user / tenant |
| Multi-agent | Sub-agents surface as tools; delegate tasks across agent instances |
| Streaming | `POST /v1/agent/stream` returns SSE token chunks |
| Webhooks | `POST /v1/triggers/webhook` — fire-and-forget HTTP trigger |
| Scheduled runs | Cron-based agent runs via APScheduler |
| Cost tracking | `cost_usd` per run via LiteLLM, logged to Langfuse |
| Auth | API key and JWT middleware on all `/v1/` routes |
| PII scrubbing | Regex-based redaction on input and output |
| Tool permissions | Allowlist which MCP tools an agent may call |
| Audit log | Structured JSON log of every tool call and LLM decision |
| Guardrails | Input/output validation via Guardrails AI |
| Observability | Full traces, spans, and scores via Langfuse |
| Evals | LLM-as-judge eval harness with golden dataset via DeepEval |

---

## Quick start

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Docker + Docker Compose](https://docs.docker.com/compose/) — for Langfuse and Qdrant
- An API key for your LLM provider (Anthropic, OpenAI, or OpenRouter)

### 1. Clone and install

```bash
git clone https://github.com/your-org/ai-agent-template
cd ai-agent-template
uv sync
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` — the minimum required fields:

```env
TENANT_ID=local-dev
LLM__PROVIDER=anthropic          # openai | anthropic | openrouter
LLM__MODEL=claude-sonnet-4-6
LLM__API_KEY=sk-ant-...
LANGFUSE__PUBLIC_KEY=pk-lf-...
LANGFUSE__SECRET_KEY=sk-lf-...
```

### 3. Start supporting services

```bash
docker compose up -d
```

This starts Langfuse (observability) and Qdrant (vector memory) locally.

### 4. Run the agent

```bash
uv run uvicorn api.main:app --reload
```

### 5. Send your first request

```bash
curl -X POST http://localhost:8000/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "local-dev",
    "input": "What can you help me with?"
  }'
```

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check — no auth required |
| `POST` | `/v1/agent/run` | Synchronous agent run — returns full response |
| `POST` | `/v1/agent/stream` | Streaming run — returns SSE token events |
| `POST` | `/v1/triggers/webhook` | Fire-and-forget trigger — returns 202 immediately |

### Run request

```json
{
  "tenant_id": "acme",
  "session_id": "optional-override",
  "user_id": "alice",
  "input": "Summarise the Q3 sales report"
}
```

### Run response

```json
{
  "session_id": "...",
  "tenant_id": "acme",
  "output": "The Q3 sales report shows...",
  "tasks_completed": [],
  "tool_calls": [],
  "cost_usd": 0.0012,
  "trace_id": "..."
}
```

### Stream response (SSE)

```
data: {"type": "token", "content": "The"}
data: {"type": "token", "content": " Q3"}
data: {"type": "done", "output": "The Q3 sales report shows..."}
data: [DONE]
```

---

## Configuration

All configuration is via environment variables using `__` as the nested delimiter.

| Env var | Default | Description |
|---|---|---|
| `LLM__PROVIDER` | — | `openai` / `anthropic` / `openrouter` |
| `LLM__MODEL` | — | Model name (e.g. `claude-sonnet-4-6`) |
| `LLM__API_KEY` | — | Provider API key |
| `MEMORY__ENABLED` | `false` | Enable Qdrant long-term memory |
| `MEMORY__SCOPE` | `user` | `session` / `user` / `tenant` / `global` |
| `AGENT__MAX_ITERATIONS` | `10` | Max reason→execute cycles per run |
| `AGENT__ALLOWED_TOOLS` | `[]` | Tool allowlist — empty = all permitted |
| `AGENT__SUB_AGENTS` | `[]` | JSON array of sub-agent configs |
| `AUTH__ENABLED` | `false` | Require `X-API-Key` or JWT on all `/v1/` routes |
| `AUTH__API_KEYS` | `[]` | Valid API keys |
| `PII__ENABLED` | `false` | Scrub PII from inputs and outputs |
| `AUDIT__ENABLED` | `false` | Write structured audit log to `audit.log` |
| `SCHEDULE__ENABLED` | `false` | Enable cron-based agent runs |
| `SCHEDULE__CRON` | `0 9 * * *` | Cron expression |

See `.env.example` for the full list.

---

## Running tests

```bash
# Unit tests
uv run pytest tests/unit/

# Integration tests
uv run pytest tests/integration/

# With coverage
uv run pytest tests/unit/ tests/integration/ --cov=src --cov-report=term-missing

# Eval suite (requires a live LLM)
uv run pytest tests/evals/ -m eval
```

---

## Examples

- [Knowledge Base Q&A](docs/examples/single-agent-kb-qa.md) — single agent answering questions from a seeded document collection
- [Web Research Pipeline](docs/examples/multi-agent-research.md) — multi-agent Perplexity-style research using Brave Search

## Documentation

- [Usage & API reference](docs/usage.md)
- [Configuration reference](.env.example)
