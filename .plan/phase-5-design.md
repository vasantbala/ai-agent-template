# Phase 5 Design — Multi-agent

**Status:** DRAFT — awaiting user approval before any code is written  
**Goal:** Let one agent delegate tasks to other agents, enabling supervisor/worker patterns without changing the core reason→execute loop.

---

## Core Design Decision

Sub-agents surface as **tools** to the parent agent's LLM. This means:
- Zero changes to the reasoning loop — the LLM already knows how to pick tools
- Sub-agent calls go through the existing execute node
- Langfuse trace continuity is preserved by passing the parent trace ID through

An agent running at `http://localhost:8002` registers as a tool called `call_research_agent`. The LLM decides when to invoke it exactly like an MCP tool, passing a natural-language task as the argument. The execute node sees the tool name, recognises it as a sub-agent, and calls the other agent's HTTP endpoint instead of an MCP server.

---

## What We're NOT Building

- Dynamic agent discovery (no service registry, no DNS)
- Sub-agents calling back to the parent (no bidirectional streaming)
- Fan-out parallelism (tasks run sequentially, as today)
- Separate deployment tooling — sub-agents are just other instances of this same template

---

## Directory Changes

```
src/
  agent/
    subagent.py     # HTTP client for calling another agent instance
    registry.py     # AgentRegistry — name → SubAgentClient + tool schemas
tests/
  unit/
    test_subagent.py
    test_agent_registry.py
```

No new top-level directories. Settings changes only in `src/config/settings.py`.

---

## Settings Changes

```python
class SubAgentConfig(BaseModel):
    name: str           # used as tool name: "call_{name}"
    url: str            # base URL of the sub-agent, e.g. "http://localhost:8002"
    description: str    # shown to the LLM in the tool schema
    timeout: float = 30.0

class AgentConfig(BaseModel):
    name: str = "ai-agent"
    version: str = "1.0.0"
    prompt_version: str = "v1"
    max_iterations: int = 10
    sub_agents: list[SubAgentConfig] = []  # NEW
```

`.env.example` addition:
```
# AGENT__SUB_AGENTS='[{"name":"researcher","url":"http://localhost:8002","description":"Searches and summarises information on a given topic."}]'
```

---

## Component Designs

### 1. SubAgentClient (`src/agent/subagent.py`)

Thin async HTTP wrapper over another agent's `/v1/agent/run` endpoint.

```python
class SubAgentError(Exception): pass

class SubAgentClient:
    def __init__(self, config: SubAgentConfig) -> None: ...

    async def call(
        self,
        task: str,
        tenant_id: str,
        session_id: str,
        user_id: str | None = None,
    ) -> str:
        # POST /v1/agent/run
        # Returns the output string from the sub-agent response.
        # Raises SubAgentError on HTTP error or timeout.
```

The `session_id` passed to the sub-agent is `{parent_session_id}-{name}-{uuid4().hex[:8]}` so it gets its own checkpoint thread while staying traceable to the parent.

**Tests:** successful call returns output, HTTP 4xx/5xx raises SubAgentError, timeout raises SubAgentError, session_id is scoped to parent+name.

---

### 2. AgentRegistry (`src/agent/registry.py`)

Holds SubAgentClients and exposes them as tool schemas the LLM can call.

```python
class AgentRegistry:
    def __init__(self, configs: list[SubAgentConfig]) -> None: ...

    def tool_schemas(self) -> list[dict]:
        # One schema per sub-agent:
        # {"name": "call_{name}", "description": ...,
        #  "input_schema": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}}

    def get(self, tool_name: str) -> SubAgentClient | None:
        # Returns client if tool_name == "call_{name}", else None.

    def is_sub_agent_tool(self, tool_name: str) -> bool: ...
```

**Tests:** empty configs → empty schemas, schema name prefixed with `call_`, unknown tool_name → None, is_sub_agent_tool matches correctly.

---

### 3. Wire into execute node (`src/agent/nodes/execute.py`)

Add a check: if the tool name matches a sub-agent, call it via AgentRegistry instead of MCPRegistry.

```python
async def execute(
    state: AgentState,
    registry: MCPRegistry,
    agent_registry: AgentRegistry | None = None,
) -> dict:
    task = state.tasks[state.current_task_index]

    if agent_registry and agent_registry.is_sub_agent_tool(task.tool_name):
        client = agent_registry.get(task.tool_name)
        result = await client.call(
            task=task.tool_args.get("task", ""),
            tenant_id=state.tenant_id,
            session_id=state.session_id,
            user_id=state.user_id,
        )
    else:
        result = await registry.call_tool(task.tool_name, task.tool_args)
```

**Tests:** sub-agent tool routes to AgentRegistry, MCP tool routes to MCPRegistry, None agent_registry falls through to MCPRegistry.

---

### 4. Wire into build_graph and API

`build_graph` gets an optional `agent_registry` parameter. The tools list passed to the reason node is extended with `agent_registry.tool_schemas()`.

```python
def build_graph(..., agent_registry: AgentRegistry | None = None):
    all_tools = mcp_tools + (agent_registry.tool_schemas() if agent_registry else [])
    # reason node uses all_tools
    # execute node receives agent_registry
```

In `main.py`:
```python
agent_registry = AgentRegistry(settings.agent.sub_agents)
graph = build_graph(..., agent_registry=agent_registry)
```

Empty `sub_agents` list → no sub-agent tools added, existing behaviour unchanged.

---

## Build Order

| # | Component | Files | Tests |
|---|---|---|---|
| 1 | SubAgentConfig in settings | `src/config/settings.py` | `test_config.py` (extend) |
| 2 | SubAgentClient | `src/agent/subagent.py` | `test_subagent.py` |
| 3 | AgentRegistry | `src/agent/registry.py` | `test_agent_registry.py` |
| 4 | Wire into execute + graph + API | `src/agent/nodes/execute.py`, `src/agent/graph.py`, `src/api/main.py` | extend existing tests |

---

## Definition of Done for Phase 5

- [ ] All unit tests pass (`pytest tests/unit/`)
- [ ] Integration tests still pass (`pytest tests/integration/`)
- [ ] Sub-agent tool appears in the LLM's tool list when `sub_agents` is non-empty
- [ ] Parent agent routes tasks to the correct sub-agent HTTP endpoint
- [ ] Empty `sub_agents` config leaves existing single-agent behaviour unaffected
