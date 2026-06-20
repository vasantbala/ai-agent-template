# Phase 1 Design — Foundation

**Status:** DRAFT — awaiting user approval before any code is written  
**Goal:** A working, observable agent you can fork and run immediately against any LLM provider.

---

## What Phase 1 Delivers

- A FastAPI microservice with a `POST /v1/agent/run` endpoint
- LangGraph-powered agentic loop: reason → execute tools → respond
- MCP server integration configurable entirely from `.env` / config
- Structured, predictable JSON responses (every time, no exceptions)
- Langfuse tracing on every run out of the box
- Basic input/output guardrails
- Versioned system prompts (no hardcoded strings)
- Multi-tenant from day one (`tenant_id` scopes everything)
- Fully Dockerised local environment

---

## Directory Structure

```
ai-agent-template/
├── src/
│   ├── agent/
│   │   ├── graph.py          # LangGraph state machine
│   │   ├── state.py          # AgentState TypedDict
│   │   └── nodes/
│   │       ├── reason.py     # Plan tasks from input
│   │       ├── execute.py    # Call MCP tools
│   │       └── respond.py    # Format structured response
│   ├── config/
│   │   ├── settings.py       # Pydantic Settings — all config lives here
│   │   └── prompts.py        # PromptManager — load versioned prompts
│   ├── llm/
│   │   └── client.py         # LiteLLM wrapper
│   ├── tools/
│   │   ├── registry.py       # Connect/disconnect MCP servers, list tools
│   │   └── client.py         # Single MCP server client
│   ├── guardrails/
│   │   ├── input.py          # Validate and sanitise inputs
│   │   └── output.py         # Enforce output schema
│   ├── observability/
│   │   └── tracer.py         # Langfuse AgentTracer
│   └── api/
│       ├── main.py           # FastAPI app factory
│       ├── schemas.py        # AgentRequest / AgentResponse
│       └── routes/
│           ├── agent.py      # POST /v1/agent/run
│           └── health.py     # GET /health
├── prompts/
│   └── v1/
│       └── system.md         # Default system prompt (version 1)
├── tests/
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_llm_client.py
│   │   ├── test_prompt_manager.py
│   │   ├── test_mcp_registry.py
│   │   ├── test_graph.py
│   │   ├── test_guardrails.py
│   │   └── test_tracer.py
│   └── integration/
│       └── test_api.py
├── docker-compose.yml        # agent + langfuse + langfuse-db
├── Dockerfile
├── pyproject.toml
└── .env.example
```

---

## Component Designs

### 1. Config (`src/config/settings.py`)

All configuration via Pydantic Settings. `__` delimiter maps env vars to nested models.

```python
class LLMSettings(BaseSettings):
    provider: Literal["openai", "anthropic", "openrouter"]
    model: str                        # e.g. "gpt-4o", "claude-sonnet-4-6"
    api_key: str
    base_url: str | None = None       # override for OpenRouter / LiteLLM proxy
    max_tokens: int = 4096
    temperature: float = 0.0

class LangfuseSettings(BaseSettings):
    public_key: str
    secret_key: str
    host: str = "https://cloud.langfuse.com"

class MCPServerConfig(BaseModel):
    name: str
    transport: Literal["stdio", "sse", "http"]
    command: str | None = None        # stdio: shell command to launch server
    args: list[str] = []
    url: str | None = None            # sse/http: server URL
    env: dict[str, str] = {}

class AgentConfig(BaseSettings):
    name: str = "ai-agent"
    version: str = "1.0.0"
    prompt_version: str = "v1"        # maps to prompts/{version}/system.md
    max_iterations: int = 10

class Settings(BaseSettings):
    tenant_id: str
    environment: Literal["development", "production"] = "development"
    llm: LLMSettings
    langfuse: LangfuseSettings
    agent: AgentConfig
    mcp_servers: list[MCPServerConfig] = []

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )
```

**`.env.example`:**
```
TENANT_ID=local-dev
ENVIRONMENT=development

LLM__PROVIDER=anthropic
LLM__MODEL=claude-sonnet-4-6
LLM__API_KEY=sk-...

LANGFUSE__PUBLIC_KEY=pk-...
LANGFUSE__SECRET_KEY=sk-...
LANGFUSE__HOST=http://localhost:3000

AGENT__NAME=my-agent
AGENT__PROMPT_VERSION=v1
AGENT__MAX_ITERATIONS=10

# MCP servers defined as JSON array
MCP_SERVERS='[{"name":"filesystem","transport":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/tmp"]}]'
```

**Tests:** Settings load correctly, missing required fields raise clear errors, nested delimiter works, MCP server list parses from JSON.

---

### 2. Prompt Manager (`src/config/prompts.py`)

Prompts live in files — never hardcoded in Python. Version is set in config.

```python
class PromptManager:
    def __init__(self, version: str, prompts_dir: Path = Path("prompts")):
        self._path = prompts_dir / version / "system.md"

    def get_system_prompt(self) -> str:
        # reads and returns the versioned system prompt
        # raises FileNotFoundError with a clear message if version doesn't exist

    def get_system_message(self) -> SystemMessage:
        # returns a LangChain SystemMessage wrapping the prompt
```

**`prompts/v1/system.md`:** A default system prompt explaining the agent's role, how to reason, and how to use tools. Forkable — the first thing someone customises when building their own agent.

**Tests:** Correct prompt loaded for version, clear error on missing version.

---

### 3. LLM Client (`src/llm/client.py`)

Thin wrapper over LiteLLM. One place to swap providers.

```python
class LLMClient:
    def __init__(self, settings: LLMSettings): ...

    async def complete(
        self,
        messages: list[BaseMessage],
        tools: list[dict] | None = None,
        response_model: type[BaseModel] | None = None,  # structured output
    ) -> AIMessage: ...
```

- Uses `litellm.acompletion` for async
- When `response_model` is set, uses LiteLLM's structured output mode (instructor-compatible)
- Provider/model/api_key/base_url all come from `LLMSettings`

**Tests:** Mock `litellm.acompletion`, assert correct messages and model passed, structured output path, error propagation.

---

### 4. MCP Registry (`src/tools/`)

Manages lifecycle of all configured MCP servers and exposes a unified tool interface to the graph.

```python
# src/tools/client.py
class MCPClient:
    def __init__(self, config: MCPServerConfig): ...
    async def connect(self) -> None: ...
    async def list_tools(self) -> list[dict]: ...        # OpenAI-compatible tool schema
    async def call_tool(self, name: str, args: dict) -> str: ...
    async def disconnect(self) -> None: ...

# src/tools/registry.py
class MCPRegistry:
    def __init__(self, configs: list[MCPServerConfig]): ...

    async def connect_all(self) -> None: ...
    async def disconnect_all(self) -> None: ...
    async def get_all_tools(self) -> list[dict]: ...     # merged from all servers
    async def call_tool(self, name: str, args: dict) -> str: ...
    # routes to the correct server by tool name
```

**Tests:** Mock MCP transport, assert tools listed correctly, assert correct server called by tool name, disconnect called on teardown.

---

### 5. Agent State and Graph (`src/agent/`)

#### State (`state.py`)

```python
class Task(BaseModel):
    id: str
    description: str
    status: Literal["pending", "in_progress", "completed", "failed"]
    tool_name: str | None = None
    tool_args: dict = {}
    result: str | None = None

class AgentState(TypedDict):
    tenant_id: str
    session_id: str
    messages: list[BaseMessage]       # full conversation history
    tasks: list[Task]                 # task list derived by reason node
    current_task_index: int
    response: AgentResponse | None
    iteration: int
    error: str | None
```

#### Graph (`graph.py`)

```
START → reason → execute → reason (loop) → respond → END
                    ↑______________|  (while tasks remain)
```

```python
def build_graph(llm: LLMClient, registry: MCPRegistry, prompts: PromptManager) -> CompiledGraph:
    ...
```

**Node responsibilities:**

- **`reason`** — sends messages to LLM with available tools, gets back a task list or a decision to respond. Increments `iteration`, raises if `max_iterations` exceeded.
- **`execute`** — takes the next pending task, calls `registry.call_tool(...)`, updates task status and result.
- **`respond`** — sends final context to LLM and gets back a structured `AgentResponse`.

**Conditional edge after `reason`:**
- If pending tasks exist → `execute`
- If no pending tasks → `respond`

**Conditional edge after `execute`:**
- Always → `reason` (re-evaluate after tool result)

**Tests:** Graph compiles, each node runs correctly with mocked dependencies, iteration limit raises, graph runs end-to-end with mocked LLM and registry.

---

### 6. Guardrails (`src/guardrails/`)

#### Input (`input.py`)

```python
class InputGuardrail:
    MAX_INPUT_LENGTH = 10_000

    def validate(self, request: AgentRequest) -> None:
        # raises GuardrailViolation if:
        # - input exceeds max length
        # - common prompt injection patterns detected
        #   (e.g. "ignore previous instructions", "you are now", "</s>")
```

#### Output (`output.py`)

```python
class OutputGuardrail:
    def validate(self, response: AgentResponse) -> AgentResponse:
        # validates response against AgentResponse schema via Guardrails AI
        # raises GuardrailViolation if schema invalid
        # returns validated (possibly coerced) response
```

**Tests:** Long input rejected, injection patterns caught, valid output passes, invalid output raises.

---

### 7. Observability (`src/observability/tracer.py`)

```python
class AgentTracer:
    def __init__(self, settings: LangfuseSettings, tenant_id: str):
        self._lf = Langfuse(
            public_key=settings.public_key,
            secret_key=settings.secret_key,
            host=settings.host,
        )
        self._tenant_id = tenant_id

    def start_trace(self, session_id: str, input: str) -> StatefulTraceClient:
        # creates trace with tenant_id as metadata
        ...

    def span(self, trace, name: str, input: dict) -> StatefulSpanClient:
        ...

    def end_span(self, span, output: dict, error: str | None = None) -> None:
        ...

    def end_trace(self, trace, output: str, usage: TokenUsage) -> None:
        ...
```

Tracer is passed into LangGraph nodes as a dependency. Each node calls `span()`/`end_span()`. The full run is wrapped in `start_trace()`/`end_trace()` at the API layer.

**Tests:** Mock Langfuse client, assert correct calls on trace/span start and end.

---

### 8. API Schemas (`src/api/schemas.py`)

```python
class AgentRequest(BaseModel):
    tenant_id: str
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    input: str
    context: dict[str, Any] = {}

class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ToolCall(BaseModel):
    tool_name: str
    args: dict[str, Any]
    result: str
    success: bool

class AgentResponse(BaseModel):
    session_id: str
    tenant_id: str
    output: str
    tasks_completed: list[Task]
    tool_calls: list[ToolCall]
    tokens_used: TokenUsage
    trace_id: str              # Langfuse trace ID — lets callers deep-link into traces
```

---

### 9. API Routes (`src/api/routes/`)

```python
# health.py
GET /health → {"status": "ok", "version": settings.agent.version}

# agent.py
POST /v1/agent/run
  - validates request via InputGuardrail
  - starts Langfuse trace
  - runs LangGraph graph
  - validates response via OutputGuardrail
  - ends Langfuse trace
  - returns AgentResponse
```

All errors return a consistent error envelope:
```json
{"error": {"code": "GUARDRAIL_VIOLATION", "message": "..."}}
```

**Integration tests:** POST to `/v1/agent/run` with mocked graph returns correct schema. `/health` returns 200.

---

### 10. Docker Compose

```yaml
services:
  agent:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [langfuse]

  langfuse:
    image: langfuse/langfuse:latest
    ports: ["3000:3000"]
    depends_on: [langfuse-db]
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse@langfuse-db/langfuse
      NEXTAUTH_SECRET: dev-secret
      NEXTAUTH_URL: http://localhost:3000

  langfuse-db:
    image: postgres:16
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse
      POSTGRES_DB: langfuse
    volumes: [langfuse-db:/var/lib/postgresql/data]

volumes:
  langfuse-db:
```

---

## Build Order

Each component is built and tested before the next begins. A component is **done** when its tests pass and it is committed.

| # | Component | File(s) | Tests |
|---|---|---|---|
| 1 | Config & settings | `src/config/settings.py`, `.env.example` | `test_config.py` |
| 2 | Prompt manager | `src/config/prompts.py`, `prompts/v1/system.md` | `test_prompt_manager.py` |
| 3 | LLM client | `src/llm/client.py` | `test_llm_client.py` |
| 4 | MCP client + registry | `src/tools/` | `test_mcp_registry.py` |
| 5 | Agent state + graph | `src/agent/` | `test_graph.py` |
| 6 | Guardrails | `src/guardrails/` | `test_guardrails.py` |
| 7 | Tracer | `src/observability/tracer.py` | `test_tracer.py` |
| 8 | API schemas + routes | `src/api/` | `test_api.py` |
| 9 | Docker Compose | `docker-compose.yml`, `Dockerfile` | smoke test: `docker compose up`, hit `/health` |

---

## Definition of Done for Phase 1

- [ ] All unit tests pass (`pytest tests/unit`)
- [ ] Integration test passes (`pytest tests/integration`)
- [ ] `docker compose up` starts cleanly
- [ ] `POST /v1/agent/run` with a real LLM and a configured MCP server returns a valid `AgentResponse`
- [ ] Run is visible in Langfuse UI with trace and spans
- [ ] `.env.example` is complete — a new user can clone, copy `.env.example` to `.env`, fill in keys, and run
