# AI Agent Template

## Goal

A reusable, forkable template for building AI agents that can be configured or extended without major refactoring. Consumed as a Docker microservice over HTTP/REST so any host product (web, .NET, Windows Forms) can integrate without caring about the internal language.

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python | Dominant AI/agent ecosystem; runs as a microservice so host language doesn't matter |
| Dependency management | uv | Fast, modern, reproducible |
| Agent framework | LangGraph | Production-grade, built-in checkpointing + HITL, multi-agent patterns |
| LLM interface | LiteLLM | Unified API across OpenAI, OpenRouter, and Anthropic |
| MCP integration | Official Python MCP SDK | First-party, keeps us aligned with the spec |
| Config | Pydantic Settings | Type-safe, nested config, `__` env var override |
| API layer | FastAPI | Async, streaming support, pairs well with LangGraph and Pydantic |
| Observability | Langfuse | Traces, spans, token usage — integrates via LangChain callbacks |
| Vector store (memory) | Qdrant | Hybrid search (dense + sparse), self-hostable via Docker |
| Guardrails | Guardrails AI | Input/output validation, schema enforcement, extensible validators |
| Evals | DeepEval | LLM-as-judge, provider-agnostic, broad metric coverage |
| Auth (Phase 7) | API keys + JWT | Stateless, simple to issue per-agent or per-user |
| Containerization | Docker + Docker Compose | Self-contained local and prod environments |
| Testing | pytest | Standard, well-supported |

---

## Design Principles

- Configuration-first: change behavior through config, not code
- Extension points over rewrites: override or compose, never gut
- Batteries included for observability and evals from day one
- Multi-tenant by default — never retrofit isolation
- Each phase ships something usable — no half-finished layers

---

## Phases

### Phase 1 — Foundation
*A working, observable agent you can fork and run immediately.*

- Config-first design with schema validation and clear error messages
- Multi-tenant foundation — tenant ID scoping in config, memory, and logs from day one
- MCP server integration — plug in one or more MCP servers to give the agent tools and context
- Core agentic loop via LangGraph — reason over inputs, derive tasks, execute them
- Structured outputs — Pydantic models + LLM structured output mode so every response has a predictable schema
- Prompt versioning — system prompts as versioned config artifacts, not hardcoded strings
- Basic guardrails — input schema validation and output schema enforcement via Guardrails AI
- Langfuse-based tracing and logging out of the box
- Docker-ready packaging

### Phase 2 — Reliability
*Make the agent production-worthy: it handles failure gracefully, stays within budget, and never acts without approval.*

- Human-in-the-loop (HITL) — LangGraph interrupt points for approval gates before consequential actions
- Context window management — summarization and pruning strategy to prevent silent degradation on long sessions
- Retry and fallback logic for MCP tool calls
- Circuit breakers for flaky MCP servers
- Token budget management to avoid runaway costs
- Checkpointing — save task state so a failed run can resume rather than restart
- Hot reload — update config and prompts without restarting

### Phase 3 — Memory
*Give the agent persistence across calls and runs.*

- Short-term working memory within a session
- Long-term memory via Qdrant for retrieval across runs
- Configurable memory scopes: per-user, per-session, per-tenant, global

### Phase 4 — Evals & Quality
*Close the feedback loop so you can measure and improve the agent.*

- LLM-as-judge eval harness via DeepEval
- Golden dataset management — store expected outputs, diff against new runs
- Cost and latency tracking per run alongside quality scores
- A/B testing between agent versions or prompt variants
- Prompt versioning ties in here — roll back bad prompts based on eval regression

### Phase 5 — Multi-agent
*Compose agents into larger systems.*

- Connect to a parent or child agent for delegation
- Supervisor/worker pattern — fan out tasks to sub-agents, aggregate results
- Agent registry so agents can discover and call each other by name
- Standardized handoff protocol for structured context passing between agents

### Phase 6 — Deployment & Triggers
*Move beyond manual invocation.*

- Streaming responses — real-time token streaming via FastAPI for responsive web/desktop UX
- Cost attribution — track spend per user, per run, per tenant with budget enforcement
- Scheduled runs (cron-style)
- Webhook and event triggers (HTTP, queue-based via SQS or Redis)

### Phase 7 — Auth & Security
*Harden the agent for shared or sensitive environments.*

- API key + JWT-based auth for all endpoints
- Advanced guardrails — NeMo Guardrails or LlamaGuard for jailbreak prevention, topic restrictions, prompt injection detection
- PII detection and scrubbing on inputs and outputs
- Per-tool permission scoping (restrict which MCP tools an agent can use)
- Secret management integration (env vars today, Vault / AWS Secrets Manager later)
- Audit log of every tool call and agent decision
