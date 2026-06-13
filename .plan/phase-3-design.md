# Phase 3 Design — Memory

**Status:** DRAFT — awaiting user approval before any code is written  
**Goal:** Give the agent persistence across calls and runs — relevant context from past sessions is available at the start of each new one.

---

## What Phase 3 Delivers

- Long-term memory via Qdrant: key facts from past runs are embedded and stored, then retrieved at the start of each new session
- Configurable memory scope: per-user, per-session, per-tenant, or global — controlled by metadata on each stored memory
- Short-term memory within a session is already handled by LangGraph state + SQLite checkpointing (Phase 2) — no changes needed
- Qdrant added to Docker Compose so it runs locally alongside the agent
- Memory is optional: disabled by default, enabled by setting `MEMORY__ENABLED=true`

---

## What We're NOT Building Yet

- Episodic memory replay (feeding entire past transcripts) — Phase 3 stores summaries, not raw transcripts
- Per-tool memory (only storing results from specific tools) — global per-run summary for now
- Memory eviction / TTL — memories persist indefinitely; eviction policy comes in Phase 6
- Distributed Qdrant (single node covers Phase 3)

---

## Directory Changes

```
src/
  memory/
    __init__.py
    config.py        # MemoryConfig (moved here from settings for clarity)
    embedding.py     # EmbeddingClient — thin LiteLLM wrapper
    store.py         # MemoryStore — Qdrant read/write
    nodes.py         # retrieve_memories graph node
config/
  settings.py        # updated: MemoryConfig + EmbeddingSettings added
agent/
  graph.py           # updated: retrieve_memories node wired at graph start
api/
  routes/agent.py    # updated: store_memories called after each run
docker-compose.yml   # updated: qdrant service added
tests/
  unit/
    test_memory_store.py
    test_embedding_client.py
    test_memory_nodes.py
```

---

## Settings Changes

```python
class EmbeddingSettings(BaseModel):
    model: str = "text-embedding-3-small"
    # falls back to LLM API key if not set
    api_key: str | None = None
    dimensions: int = 1536

class MemoryConfig(BaseModel):
    enabled: bool = False
    scope: Literal["session", "user", "tenant", "global"] = "user"
    top_k: int = 5                          # memories retrieved per run
    collection_name: str = "agent_memories"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None

class Settings(BaseSettings):
    ...
    memory: MemoryConfig = MemoryConfig()
    embedding: EmbeddingSettings = EmbeddingSettings()
```

`.env.example` additions:
```
MEMORY__ENABLED=false
MEMORY__SCOPE=user
MEMORY__TOP_K=5
MEMORY__QDRANT_URL=http://localhost:6333
EMBEDDING__MODEL=text-embedding-3-small
```

---

## Component Designs

### 1. EmbeddingClient (`src/memory/embedding.py`)

Thin wrapper around `litellm.aembedding()`. Kept separate from `LLMClient` because embedding calls have different response shapes and don't need the same tool/format options.

```python
class EmbeddingClient:
    def __init__(self, settings: EmbeddingSettings, llm_api_key: str): ...

    async def embed(self, text: str) -> list[float]:
        # Calls litellm.aembedding(model=..., input=[text])
        # Returns the first embedding vector.
```

**Tests:** returns a list of floats, uses correct model string, falls back to llm_api_key when embedding api_key is None.

---

### 2. MemoryStore (`src/memory/store.py`)

Qdrant wrapper. Each stored memory is a vector + payload. The payload carries scope metadata so retrieval can be filtered.

```python
class Memory(BaseModel):
    text: str
    tenant_id: str
    session_id: str
    user_id: str | None = None
    created_at: str  # ISO timestamp

class MemoryStore:
    def __init__(self, config: MemoryConfig, embedder: EmbeddingClient): ...

    async def ensure_collection(self) -> None:
        # Create Qdrant collection if it doesn't exist.

    async def store(self, memory: Memory) -> None:
        # Embed memory.text, upsert into Qdrant with payload.

    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        scope: Literal["session", "user", "tenant", "global"],
        session_id: str | None = None,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> list[str]:
        # Embed query, search Qdrant with metadata filter based on scope.
        # Returns list of memory texts (most relevant first).
```

**Scope → filter mapping:**

| Scope | Qdrant filter |
|---|---|
| `session` | `tenant_id == X AND session_id == Y` |
| `user` | `tenant_id == X AND user_id == Y` |
| `tenant` | `tenant_id == X` |
| `global` | *(no filter)* |

**Tests:** stores a memory and retrieves it, scope filter narrows results correctly, returns empty list when collection is empty, top_k limits results.

---

### 3. retrieve_memories node (`src/memory/nodes.py`)

Graph node that runs before the first `reason` call. Retrieves relevant memories and injects them into the messages as a `SystemMessage` addendum.

```python
async def retrieve_memories(
    state: AgentState,
    store: MemoryStore,
    config: MemoryConfig,
) -> dict:
    if not config.enabled:
        return {}

    memories = await store.retrieve(
        query=state.messages[-1].content,  # last human message
        tenant_id=state.tenant_id,
        scope=config.scope,
        session_id=state.session_id,
        top_k=config.top_k,
    )

    if not memories:
        return {}

    memory_text = "\n".join(f"- {m}" for m in memories)
    context_msg = SystemMessage(
        content=f"Relevant context from past sessions:\n{memory_text}"
    )
    return {"messages": [context_msg]}
```

**Tests:** returns empty dict when memory disabled, returns empty dict when no memories found, injects SystemMessage when memories exist, uses last human message as query.

---

### 4. store_memories (API route, not a graph node)

After `run_agent` returns, the API route summarises the run and stores it as a memory. Not a graph node because it's a side-effect that happens once per request, not part of the agent loop.

```python
# In api/routes/agent.py, after run_agent():
if settings.memory.enabled:
    summary = _summarise_run(final_state)   # 1-2 sentence summary of what happened
    await memory_store.store(Memory(
        text=summary,
        tenant_id=body.tenant_id,
        session_id=body.session_id,
    ))
```

`_summarise_run` extracts a one-sentence summary from the final state's messages using the last AI message content (no extra LLM call needed).

---

## Updated Graph Flow

```
START → retrieve_memories → reason → execute → reason (loop) → END
```

`retrieve_memories` is always the first node. When `memory.enabled = false` it's a no-op (returns `{}`), so no conditional needed.

---

## Docker Compose Change

```yaml
qdrant:
  image: qdrant/qdrant:latest
  ports:
    - "6333:6333"
  volumes:
    - qdrant_data:/qdrant/storage
```

---

## Build Order

| # | Component | Files | Tests |
|---|---|---|---|
| 1 | MemoryConfig + EmbeddingSettings | `src/config/settings.py` | `test_config.py` (extend) |
| 2 | EmbeddingClient | `src/memory/embedding.py` | `test_embedding_client.py` |
| 3 | MemoryStore | `src/memory/store.py` | `test_memory_store.py` |
| 4 | retrieve_memories node | `src/memory/nodes.py` | `test_memory_nodes.py` |
| 5 | Wire into graph + API route | `src/agent/graph.py`, `src/api/routes/agent.py`, `src/api/main.py` | existing tests pass |
| 6 | Docker Compose Qdrant | `docker-compose.yml` | manual verify |

---

## Definition of Done for Phase 3

- [ ] All unit tests pass (`pytest tests/unit/`)
- [ ] Integration tests still pass (`pytest tests/integration/`)
- [ ] Functional smoke test still passes (`pytest tests/functional/`)
- [ ] Manually verified: run agent twice with same session; second run receives memories from first
- [ ] Manually verified: `MEMORY__SCOPE=tenant` retrieves memories across sessions for the same tenant
- [ ] Manually verified: `MEMORY__ENABLED=false` produces identical behavior to Phase 2 baseline
