# Phase 2 Design — Reliability

**Status:** DRAFT — awaiting user approval before any code is written  
**Goal:** Make the agent production-worthy — it handles failure gracefully, respects token budgets, survives restarts, and never acts without approval when configured to require it.

---

## What Phase 2 Delivers

- MCP tool calls retry automatically on transient failure with exponential backoff
- A circuit breaker per MCP server prevents a flaky server from cascading failures
- Token budget enforcement stops a run before it exceeds a configured spend limit
- Checkpointing via LangGraph's built-in SQLite persister — a failed run resumes from its last completed node, not from scratch
- Human-in-the-loop (HITL) interrupt point — the agent pauses before executing any tool call and waits for approval when enabled
- Context window management — the message history is summarised when it exceeds a configurable token threshold, preventing silent LLM degradation
- Hot reload — prompt version and agent config reload from disk on each request without restarting the process

---

## What We're NOT Building Yet

- Distributed checkpointing (Postgres, Redis) — SQLite covers single-instance; distributed comes in Phase 6
- Per-user token budgets — single global budget per run for now; per-tenant billing in Phase 6
- Full conversation history across sessions — that's Phase 3 (Memory)

---

## Directory Changes

```
src/
  reliability/
    __init__.py
    retry.py          # retry_tool() — exponential backoff for MCP tool calls
    circuit_breaker.py # CircuitBreaker — per-server open/half-open/closed state
    budget.py         # TokenBudget — track and enforce token spend per run
    context.py        # ContextManager — summarise/prune message history
  agent/
    graph.py          # updated: checkpoint, HITL node, context management
    nodes/
      hitl.py         # new: human_approval node
      summarise.py    # new: summarise_context node
config/
  settings.py         # updated: ReliabilityConfig added
tests/
  unit/
    test_retry.py
    test_circuit_breaker.py
    test_budget.py
    test_context.py
    test_hitl.py
```

---

## Component Designs

### 1. Retry (`src/reliability/retry.py`)

Wraps MCP tool calls with exponential backoff. Transient errors (network, timeout) are retried; permanent errors (unknown tool, bad args) are not.

```python
TRANSIENT_EXCEPTIONS = (TimeoutError, ConnectionError, OSError)

async def retry_tool(
    fn: Callable[..., Awaitable[str]],
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> str:
    # Attempt fn(*args) up to max_attempts times.
    # On transient failure: sleep min(base_delay * 2^attempt, max_delay), then retry.
    # On final failure: re-raise the last exception.
    # On non-transient failure: raise immediately without retry.
```

`MCPRegistry.call_tool()` will wrap its call in `retry_tool()`.

**Tests:** succeeds on first try, succeeds on second try after transient failure, raises after max attempts, non-transient errors are not retried, backoff delay grows exponentially.

---

### 2. Circuit Breaker (`src/reliability/circuit_breaker.py`)

Per-MCP-server state machine. Prevents hammering a server that's consistently failing.

```
CLOSED → (failure_threshold reached) → OPEN → (reset_timeout elapsed) → HALF_OPEN
HALF_OPEN → (success) → CLOSED
HALF_OPEN → (failure) → OPEN
```

```python
class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
    ): ...

    async def call(self, fn: Callable[..., Awaitable[T]], *args) -> T:
        # If OPEN and timeout not elapsed: raise CircuitOpenError immediately.
        # If OPEN and timeout elapsed: transition to HALF_OPEN, allow one attempt.
        # On success: transition to CLOSED, reset counter.
        # On failure: increment counter; if threshold reached, transition to OPEN.

    @property
    def state(self) -> Literal["closed", "open", "half_open"]: ...
```

`MCPRegistry` will own one `CircuitBreaker` per server, wrapping all tool calls.

**Tests:** starts closed, opens after threshold failures, raises immediately when open, transitions to half-open after timeout, closes on half-open success, re-opens on half-open failure.

---

### 3. Token Budget (`src/reliability/budget.py`)

Tracks cumulative token usage across all LLM calls in a run and raises before a call that would exceed the budget.

```python
class BudgetExceededError(Exception):
    pass

class TokenBudget:
    def __init__(self, max_tokens: int): ...

    def record(self, prompt_tokens: int, completion_tokens: int) -> None:
        # Add to running total. Raise BudgetExceededError if total exceeds max.

    @property
    def used(self) -> int: ...

    @property
    def remaining(self) -> int: ...
```

The `reason` node will call `budget.record()` after each LLM response. If `BudgetExceededError` is raised, the graph routes to `respond` with whatever it has.

**Settings addition:**
```python
class ReliabilityConfig(BaseModel):
    max_tokens_per_run: int = 50_000    # hard stop per agent run
    mcp_retry_attempts: int = 3
    mcp_retry_base_delay: float = 1.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_timeout: float = 60.0
    context_window_threshold: int = 6_000   # tokens before summarisation kicks in
    hitl_enabled: bool = False              # require approval before tool calls
```

**Tests:** records usage correctly, raises on budget exceeded, remaining decrements correctly.

---

### 4. Context Manager (`src/reliability/context.py`)

When message history grows beyond `context_window_threshold` tokens, summarise the middle of the conversation and replace it with a single summary message. The system prompt and the most recent N messages are always preserved.

```python
class ContextManager:
    def __init__(self, llm: LLMClient, threshold_tokens: int, preserve_last_n: int = 4):
        ...

    async def maybe_summarise(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        # Estimate token count (character-based approximation: chars / 4).
        # If under threshold: return messages unchanged.
        # If over threshold:
        #   - Keep system message (index 0) + last preserve_last_n messages.
        #   - Summarise the middle chunk via LLM.
        #   - Return [system_msg, SummaryMessage, ...last_n_messages].
```

Called at the start of the `reason` node before passing messages to the LLM.

**Tests:** returns unchanged when under threshold, summarises when over threshold, always preserves system message, always preserves last N messages, summary replaces middle messages.

---

### 5. HITL Node (`src/agent/nodes/hitl.py`)

LangGraph interrupt that pauses the graph before tool execution and waits for external approval. Only active when `reliability.hitl_enabled = true`.

```python
from langgraph.types import interrupt

async def human_approval(state: AgentState) -> dict:
    # If no pending tasks: pass through.
    pending = [t for t in state.tasks if t.status == "pending"]
    if not pending:
        return {}

    # Interrupt the graph — execution pauses here.
    # The caller resumes the graph by invoking it again with a Command(resume=approval).
    decision = interrupt({
        "question": "Approve the following tool calls?",
        "tasks": [{"tool": t.tool_name, "args": t.tool_args} for t in pending],
    })

    # decision is the value passed back by the caller on resume.
    if decision != "approved":
        return {"error": f"Tool calls rejected by human: {decision}"}
    return {}
```

Graph wiring when HITL is enabled:
```
reason → hitl → execute → reason (loop)
```
When disabled, `hitl` is bypassed: `reason → execute`.

**Tests:** passes through when no pending tasks, interrupts with correct task info when tasks exist, routes to error on rejection, passes through on approval.

---

### 6. Hot Reload (`src/config/prompts.py` update)

`PromptManager.get_system_prompt()` already reads from disk on every call — no caching. This means prompt version changes take effect on the next request automatically.

For agent config (max_iterations, hitl_enabled, etc.): `Settings` is a singleton. We expose a `reload_settings()` that resets the singleton, forcing the next `get_settings()` call to re-read from `.env`. This is called explicitly (e.g. via a `POST /admin/reload` endpoint added in Phase 6).

No code changes needed in Phase 2 for hot reload — `PromptManager` already does it. Document the pattern and add a test confirming `get_system_prompt()` picks up file changes without restart.

---

## Updated Graph Flow

### Without HITL (default)
```
START → [summarise_context] → reason → execute → reason (loop) → END
```

### With HITL enabled
```
START → [summarise_context] → reason → hitl → execute → reason (loop) → END
```

Context summarisation happens inline at the start of each `reason` call.

---

## Settings Changes

```python
# src/config/settings.py — add ReliabilityConfig
class ReliabilityConfig(BaseModel):
    max_tokens_per_run: int = 50_000
    mcp_retry_attempts: int = 3
    mcp_retry_base_delay: float = 1.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_timeout: float = 60.0
    context_window_threshold: int = 6_000
    hitl_enabled: bool = False

class Settings(BaseSettings):
    ...
    reliability: ReliabilityConfig = ReliabilityConfig()
```

`.env.example` additions:
```
RELIABILITY__MAX_TOKENS_PER_RUN=50000
RELIABILITY__HITL_ENABLED=false
RELIABILITY__CONTEXT_WINDOW_THRESHOLD=6000
```

---

## Checkpointing

LangGraph ships a `SqliteSaver` checkpointer. Enabling it means:
- Every graph node result is persisted to a local SQLite DB
- If a run fails mid-way, resuming with the same `thread_id` replays from the last successful node
- Requires passing `thread_id` (= `session_id`) in the graph config

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)
```

The checkpointer is created once at app startup (lifespan) and shared across requests.

**Tests:** graph resumes from last completed node after simulated mid-run failure.

---

## Build Order

| # | Component | Files | Tests |
|---|---|---|---|
| 1 | ReliabilityConfig in settings | `src/config/settings.py` | `test_config.py` (extend) |
| 2 | Retry | `src/reliability/retry.py` | `test_retry.py` |
| 3 | Circuit breaker | `src/reliability/circuit_breaker.py` | `test_circuit_breaker.py` |
| 4 | Token budget | `src/reliability/budget.py` | `test_budget.py` |
| 5 | Context manager | `src/reliability/context.py` | `test_context.py` |
| 6 | HITL node | `src/agent/nodes/hitl.py` | `test_hitl.py` |
| 7 | Checkpointing | `src/agent/graph.py` (update), `src/api/main.py` (update) | `test_graph.py` (extend) |
| 8 | Wire into MCPRegistry + graph | `src/tools/registry.py`, `src/agent/graph.py` | existing tests pass |

---

## Definition of Done for Phase 2

- [ ] All unit tests pass (`pytest tests/unit/`)
- [ ] Integration tests still pass (`pytest tests/integration/`)
- [ ] Functional smoke test still passes (`pytest tests/functional/`)
- [ ] Manually verified: run fails mid-way (kill process), restart resumes from checkpoint
- [ ] Manually verified: HITL interrupt pauses graph and resumes on approval
- [ ] Manually verified: a run with a token budget of 100 tokens raises `BudgetExceededError` gracefully
