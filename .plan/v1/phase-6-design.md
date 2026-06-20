# Phase 6 Design — Deployment & Triggers

**Status:** DRAFT — awaiting user approval before any code is written  
**Goal:** Move beyond request/response — stream tokens in real time, track cost, and let external systems trigger runs via webhooks or cron.

---

## What Phase 6 Delivers

- **Streaming** — `POST /v1/agent/stream` returns SSE token chunks as they arrive, so web/desktop consumers feel immediate response
- **Cost tracking** — `cost_usd` accumulated per run using LiteLLM's cost model; logged to Langfuse alongside the trace
- **Webhook trigger** — `POST /v1/triggers/webhook` converts an HTTP payload to an agent run (fire-and-forget, async)
- **Scheduled runs** — APScheduler cron job configured entirely from env vars; triggers the agent on a schedule with a preset input

---

## What We're NOT Building

- Queue-based triggers (SQS, Redis) — deferred; webhook covers the common case
- Per-tenant cost budgets with enforcement gates — deferred to Phase 7
- WebSocket streaming — SSE is sufficient for one-way token streams and simpler to consume from .NET

---

## Directory Changes

```
src/
  api/
    routes/
      stream.py       # POST /v1/agent/stream  (new)
      webhook.py      # POST /v1/triggers/webhook  (new)
  triggers/
    __init__.py
    scheduler.py      # APScheduler cron job setup
tests/
  unit/
    test_stream.py
    test_webhook.py
    test_scheduler.py
  integration/
    test_stream_api.py
```

---

## Settings Changes

```python
class CostConfig(BaseModel):
    enabled: bool = True   # compute and log cost_usd after every run

class ScheduleConfig(BaseModel):
    enabled: bool = False
    cron: str = "0 9 * * *"        # standard cron expression
    input: str = ""                 # agent input to send on each tick
    tenant_id: str = ""             # tenant to run as
    session_id_prefix: str = "scheduled"

class Settings(BaseSettings):
    ...
    cost: CostConfig = CostConfig()
    schedule: ScheduleConfig = ScheduleConfig()
```

`.env.example` additions:
```
COST__ENABLED=true
# SCHEDULE__ENABLED=false
# SCHEDULE__CRON="0 9 * * *"
# SCHEDULE__INPUT="Run daily digest"
# SCHEDULE__TENANT_ID=local-dev
```

---

## AgentState Change

```python
class AgentState(BaseModel):
    ...
    cost_usd: float = 0.0   # NEW — accumulated across the run
```

---

## Component Designs

### 1. Cost tracking in reason node

After each LLM call, compute cost using `litellm.completion_cost()` and accumulate it in state.

```python
# In reason node, after the LLM call:
import litellm
cost = litellm.completion_cost(completion_response=response) or 0.0
total_cost = state.cost_usd + cost
return {..., "cost_usd": total_cost}
```

The final `cost_usd` is returned in `AgentResponse` and logged to Langfuse as a score named `"cost_usd"`.

**Settings**: `cost.enabled` gates the calculation — when False, `cost_usd` stays 0.

**Tests**: cost accumulated across iterations, disabled when `cost.enabled=False`, zero on unknown model.

---

### 2. Streaming endpoint (`src/api/routes/stream.py`)

Uses LangGraph's `astream_events` to emit SSE token chunks as the agent reasons.

```
POST /v1/agent/stream
Content-Type: application/json → same body as /v1/agent/run

Response: text/event-stream
data: {"type": "token", "content": "Paris"}
data: {"type": "token", "content": " is"}
...
data: {"type": "done", "session_id": "...", "output": "Paris is the capital..."}
data: [DONE]
```

Implementation:
```python
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk

async def token_stream(graph, state, config):
    output_tokens = []
    async for event in graph.astream_events(state, config, version="v2"):
        if event["event"] == "on_chat_model_stream":
            chunk: AIMessageChunk = event["data"]["chunk"]
            if chunk.content:
                yield f'data: {{"type":"token","content":{json.dumps(chunk.content)}}}\n\n'
                output_tokens.append(chunk.content)
    full_output = "".join(output_tokens)
    yield f'data: {{"type":"done","output":{json.dumps(full_output)}}}\n\n'
    yield "data: [DONE]\n\n"
```

**Tests**: stream emits token events, final event is `done`, `[DONE]` terminates the stream.

---

### 3. Webhook trigger (`src/api/routes/webhook.py`)

Accepts an arbitrary JSON payload, converts it to an agent run via a configurable input template, and runs the agent as a FastAPI background task.

```
POST /v1/triggers/webhook
Content-Type: application/json
{
  "tenant_id": "acme",
  "input": "Process this event: ...",   ← caller provides the agent input directly
  "session_id": "optional-override"
}

Response 202:
{"accepted": true, "session_id": "wh-abc123"}
```

The run happens in a FastAPI `BackgroundTask` — the HTTP response returns immediately, the agent runs async. No result is returned via this endpoint (use the normal `/v1/agent/run` if you need a synchronous result).

**Tests**: returns 202, session_id present in response, background task is queued, missing tenant_id returns 422.

---

### 4. Scheduled runs (`src/triggers/scheduler.py`)

APScheduler `AsyncIOScheduler` started in FastAPI lifespan. On each tick it calls `run_agent` with the configured input and tenant.

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

def start_scheduler(app: FastAPI, settings: Settings) -> AsyncIOScheduler:
    if not settings.schedule.enabled:
        return None

    scheduler = AsyncIOScheduler()

    async def _run():
        session_id = f"{settings.schedule.session_id_prefix}-{uuid4().hex[:8]}"
        await run_agent(
            graph=app.state.graph,
            tenant_id=settings.schedule.tenant_id,
            session_id=session_id,
            user_input=settings.schedule.input,
            system_prompt=app.state.prompts.get_system_prompt(),
        )

    scheduler.add_job(
        _run,
        CronTrigger.from_crontab(settings.schedule.cron),
    )
    scheduler.start()
    return scheduler
```

Scheduler is started in `lifespan` and shut down on exit.

**Tests**: scheduler not started when disabled, job added with correct cron, `_run` calls `run_agent` with correct args.

---

## API Response Change

`AgentResponse` gains `cost_usd`:

```python
class AgentResponse(BaseModel):
    ...
    cost_usd: float = 0.0
```

---

## Build Order

| # | Component | Files | Tests |
|---|---|---|---|
| 1 | CostConfig + ScheduleConfig in settings | `src/config/settings.py` | `test_config.py` (extend) |
| 2 | Cost tracking in reason node + AgentState | `src/agent/state.py`, `src/agent/nodes/reason.py` | extend `test_graph.py` |
| 3 | Streaming endpoint | `src/api/routes/stream.py` | `test_stream.py`, `test_stream_api.py` |
| 4 | Webhook trigger | `src/api/routes/webhook.py` | `test_webhook.py` |
| 5 | Scheduled runs | `src/triggers/scheduler.py` | `test_scheduler.py` |

---

## Definition of Done for Phase 6

- [ ] All unit tests pass (`pytest tests/unit/`)
- [ ] Integration tests still pass (`pytest tests/integration/`)
- [ ] `POST /v1/agent/stream` returns SSE token events for a real LLM call
- [ ] `cost_usd` appears in `AgentResponse` and in Langfuse as a score
- [ ] `POST /v1/triggers/webhook` returns 202 and runs the agent in the background
- [ ] Scheduler fires on the configured cron when `SCHEDULE__ENABLED=true`
