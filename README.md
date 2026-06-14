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
PYTHONPATH=src uv run uvicorn api.main:app --reload
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
| `POST` | `/v1/kb/seed` | Seed documents into the vector knowledge base |

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

All configuration is via environment variables. Use `__` as the nested delimiter (e.g. `LLM__API_KEY`). See `.env.example` for a ready-to-copy template.

### LLM

| Env var | Default | Description |
|---|---|---|
| `LLM__PROVIDER` | — | `openai` / `anthropic` / `openrouter` |
| `LLM__MODEL` | — | Model name (e.g. `claude-sonnet-4-6`, `gpt-4o`) |
| `LLM__API_KEY` | — | Provider API key |
| `LLM__BASE_URL` | `null` | Override base URL (OpenRouter / LiteLLM proxy) |
| `LLM__MAX_TOKENS` | `4096` | Max tokens per LLM call |
| `LLM__TEMPERATURE` | `0.0` | LLM temperature |

### Agent

| Env var | Default | Description |
|---|---|---|
| `AGENT__NAME` | `ai-agent` | Agent name — appears in Langfuse traces |
| `AGENT__VERSION` | `1.0.0` | Version string for traces |
| `AGENT__PROMPT_VERSION` | `v1` | Prompt directory under `prompts/` |
| `AGENT__MAX_ITERATIONS` | `10` | Max reason→execute cycles per run |
| `AGENT__ALLOWED_TOOLS` | `[]` | Tool allowlist — empty = all permitted |
| `AGENT__SUB_AGENTS` | `[]` | JSON array of sub-agent configs |

### Reliability

| Env var | Default | Description |
|---|---|---|
| `RELIABILITY__MAX_TOKENS_PER_RUN` | `50000` | Token budget per run — error returned if exceeded |
| `RELIABILITY__MCP_RETRY_ATTEMPTS` | `3` | Retry attempts on failed MCP tool calls |
| `RELIABILITY__MCP_RETRY_BASE_DELAY` | `1.0` | Exponential backoff base delay (seconds) |
| `RELIABILITY__CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Consecutive failures before circuit opens |
| `RELIABILITY__CIRCUIT_BREAKER_RESET_TIMEOUT` | `60.0` | Seconds before circuit tries to close |
| `RELIABILITY__CONTEXT_WINDOW_THRESHOLD` | `6000` | Token count that triggers conversation summarisation |
| `RELIABILITY__HITL_ENABLED` | `false` | Pause before each tool call for human approval |

### Memory & Embedding

| Env var | Default | Description |
|---|---|---|
| `MEMORY__ENABLED` | `false` | Enable Qdrant long-term memory |
| `MEMORY__SCOPE` | `user` | `session` / `user` / `tenant` / `global` — see below |
| `MEMORY__TOP_K` | `5` | Retrieved chunks per query |
| `MEMORY__COLLECTION_NAME` | `agent_memories` | Qdrant collection name |
| `MEMORY__QDRANT_URL` | `http://localhost:6333` | Qdrant instance URL |
| `MEMORY__QDRANT_API_KEY` | `null` | Qdrant Cloud API key (self-hosted: leave unset) |
| `EMBEDDING__MODEL` | `text-embedding-3-small` | Embedding model |
| `EMBEDDING__API_KEY` | `null` | Embedding API key (falls back to `LLM__API_KEY`) |
| `EMBEDDING__DIMENSIONS` | `1536` | Vector dimensions (must match the chosen model) |

**Memory scope values:**

| Scope | Isolation | Use case |
|---|---|---|
| `session` | Unique per conversation | Ephemeral working memory for one chat |
| `user` | Shared across a user's sessions | Personalised assistant that remembers the user |
| `tenant` | Shared across all users in a tenant | Shared knowledge base / FAQ agent |
| `global` | No isolation | Single-tenant deployments |

### Auth

| Env var | Default | Description |
|---|---|---|
| `AUTH__ENABLED` | `false` | Require auth on all `/v1/` routes |
| `AUTH__API_KEYS` | `[]` | Valid API key strings (`X-API-Key` header) |
| `AUTH__JWT_SECRET` | `null` | JWT signing secret |
| `AUTH__JWT_ALGORITHM` | `HS256` | JWT algorithm |

### Security

| Env var | Default | Description |
|---|---|---|
| `PII__ENABLED` | `false` | Scrub PII from input and output |
| `PII__PATTERNS` | `[email,phone,ssn,credit_card]` | Patterns: `email` `phone` `ssn` `credit_card` `ip_address` |
| `PII__REPLACEMENT` | `[REDACTED]` | Replacement string for matched PII |
| `AUDIT__ENABLED` | `false` | Write structured JSON audit log |
| `AUDIT__LOG_PATH` | `audit.log` | Audit log file path (`""` = stdout only) |

### Cost & Scheduling

| Env var | Default | Description |
|---|---|---|
| `COST__ENABLED` | `true` | Track `cost_usd` per run via LiteLLM |
| `SCHEDULE__ENABLED` | `false` | Enable cron-based scheduled runs |
| `SCHEDULE__CRON` | `0 9 * * *` | Cron expression |
| `SCHEDULE__INPUT` | `""` | Task text sent on each scheduled run |
| `SCHEDULE__TENANT_ID` | `""` | Tenant for scheduled runs |
| `SCHEDULE__SESSION_ID_PREFIX` | `scheduled` | Session ID prefix for scheduled runs |

### Evals

| Env var | Default | Description |
|---|---|---|
| `EVAL__ENABLED` | `false` | Enable eval harness |
| `EVAL__METRICS` | `[correctness]` | `correctness` / `faithfulness` / `relevancy` |
| `EVAL__THRESHOLD` | `0.7` | Minimum passing score (0–1) |
| `EVAL__MODEL` | `gpt-4o` | LLM-as-judge model |
| `EVAL__GOLDEN_DATASET_PATH` | `evals/golden/default.json` | Path to golden test cases |

---

## Demo UI

A Gradio chat interface for testing the agent interactively — no curl required. Ships as a separate overlay so the core `docker-compose.yml` is unchanged.

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml up --build
```

Open **http://localhost:7860**. Features:

- Real-time streaming chat (tokens appear as they arrive)
- KB Seeder tab — paste documents directly into Qdrant
- Config sidebar — set agent URL, tenant ID, and API key at runtime

To pass an API key when `AUTH__ENABLED=true`:

```bash
AGENT_API_KEY=sk-agent-abc123 docker compose \
  -f docker-compose.yml -f docker-compose.demo.yml up --build
```

> The demo UI is for development and manual testing only. Do not include it in production deployments.

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
