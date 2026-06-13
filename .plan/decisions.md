# Decision Log

Non-obvious decisions and the reasoning behind them. Read this before relitigating any choice.

---

## Language: Python over TypeScript

**Decision:** Python  
**Why:** The template runs as a standalone microservice over HTTP/REST. The host product (Certify, web apps) speaks HTTP — the internal language is invisible to consumers. Given that, Python wins on ecosystem maturity: LangGraph Python SDK is significantly more complete than LangGraph.js, LiteLLM and DeepEval are Python-only, and the entire agentic AI community moves Python-first.  
**TypeScript would win if:** The agent were embedded directly in a Node.js/web frontend rather than running as a separate service.

---

## Agent Framework: LangGraph over Pydantic AI

**Decision:** LangGraph  
**Why:** LangGraph is production-grade and used at scale (LinkedIn, Elastic, Replit). It provides built-in checkpointing (covers Phase 2 for free), first-class human-in-the-loop interrupt points, and mature multi-agent supervisor/worker patterns. The "LangChain is only for prototypes" reputation applies to the old chains/agents API — LangGraph is a different, lower-level product.  
**Pydantic AI would win if:** We prioritised a cleaner, more type-safe API over ecosystem maturity and were willing to build multi-agent patterns ourselves.

---

## LLM Interface: LiteLLM

**Decision:** LiteLLM  
**Why:** Single unified API across OpenAI, OpenRouter, and Anthropic. Swap providers via config with no code changes. Essential for a template meant to work with multiple providers.

---

## Vector Store: Qdrant over pgvector / Chroma

**Decision:** Qdrant  
**Why:** Best hybrid search (dense + sparse vectors in one query), self-hostable via Docker with no extra infrastructure, strong Python SDK. pgvector requires Postgres; Chroma lacks production-scale hybrid search.

---

## Evals: DeepEval over RAGAS

**Decision:** DeepEval  
**Why:** Provider-agnostic LLM-as-judge, works with OpenAI/Anthropic/LiteLLM, broader metric coverage beyond RAG-specific metrics. RAGAS is excellent for RAG pipelines specifically but too narrow for general agent evals.

---

## Auth: API Keys + JWT over OAuth2/OIDC

**Decision:** API keys + JWT  
**Why:** Stateless, simple to issue per-agent or per-user, easy for .NET/Windows Forms consumers to attach to HTTP requests. OAuth2/OIDC is better for multi-tenant human-facing UIs — a later concern (Phase 7) not worth the complexity now.

---

## Guardrails: Guardrails AI (basic) + NeMo/LlamaGuard (advanced, Phase 7)

**Decision:** Two-tier approach  
**Why:** Guardrails AI handles schema enforcement and basic validation (Phase 1) cheaply. NeMo Guardrails / LlamaGuard add conversational guardrails, jailbreak prevention, and PII scrubbing (Phase 7) — deferring these avoids over-engineering early but the hooks are in place.

---

## Multi-tenancy: Foundation in Phase 1

**Decision:** Tenant ID scoping from day one  
**Why:** Retrofitting multi-tenancy into memory, config, and audit logs after the fact is extremely painful. Adding a `tenant_id` field to all data models and scoping all queries from the start costs almost nothing and prevents a major refactor later.

---

## Consumption Model: Microservice over HTTP/REST

**Decision:** Standalone Docker microservice with FastAPI  
**Why:** The primary consumer is Worksoft Certify — a .NET/Windows Forms desktop app. Neither Python nor TypeScript is native to .NET. Running the agent as a microservice means Certify (or any web product) calls HTTP endpoints, and the internal implementation is completely decoupled from the host.
