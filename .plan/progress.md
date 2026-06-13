# Progress

## Current Status

**Phase:** Phase 1 complete — ready to design Phase 2  
**Last updated:** 2026-06-13

## What's Done

- [x] Vision and goal defined
- [x] All 7 phases scoped and documented (`initial-idea.md`)
- [x] Tech stack decided (LangGraph, LiteLLM, FastAPI, Qdrant, Guardrails AI, DeepEval, Langfuse)
- [x] Key design principles established (config-first, multi-tenant by default, design-before-code)
- [x] Working methodology established (CLAUDE.md, design docs, progress tracking, stop hook)
- [x] `decisions.md` created with rationale for all major choices

## What's Next

- [x] User approved `.plan/phase-1-design.md` on 2026-06-13
- [x] Component 1: Config & settings — 20 tests green, committed
- [x] Component 2: Prompt manager — 6 tests green
- [x] Component 3: LLM client — 12 tests green
- [x] Component 4: MCP client + registry — 9 tests green
- [x] Component 5: Agent state + LangGraph — 14 tests green
- [x] Component 6: Guardrails — 16 tests green
- [x] Component 7: Langfuse tracer — 6 tests green
- [x] Component 8: FastAPI routes — 7 integration tests green
- [x] Component 9: Dockerfile + Docker Compose

**Phase 1 complete — 90/90 tests passing**

## What's Next (Phase 3)

- [x] User approved `.plan/phase-3-design.md` on 2026-06-13
- [x] Component 1: MemoryConfig + EmbeddingSettings — 11 tests green
- [x] Component 2: EmbeddingClient — 5 tests green
- [x] Component 3: MemoryStore (Qdrant) — 14 tests green
- [x] Component 4: retrieve_memories node — 8 tests green
- [x] Component 5: Wire into graph + API route — 184 total tests green
- [x] Component 6: Docker Compose Qdrant

**Phase 3 complete — 184 tests passing (177 unit + 7 integration)**

---

## Phase 2 History

- [x] User approved `.plan/phase-2-design.md` on 2026-06-13
- [x] Component 1: ReliabilityConfig — 6 tests green
- [x] Component 2: Retry (exponential backoff) — 8 tests green
- [x] Component 3: Circuit breaker — 9 tests green
- [x] Component 4: Token budget — 9 tests green
- [x] Component 5: Context manager — 9 tests green
- [x] Component 6: HITL node — 6 tests green
- [x] Component 7: Checkpointing (AsyncSqliteSaver) — 3 new tests green
- [x] Component 8: Wired retry + circuit breaker into MCPRegistry

**Phase 2 complete — 146 tests passing (139 unit + 7 integration)**

Graph wiring fully complete:
- `reason` node calls `ContextManager.maybe_summarise()` before each LLM call
- `reason` node accumulates `tokens_used` in state and returns error when `max_tokens_per_run` is exceeded
- `build_graph` wires HITL node conditionally: `reason → hitl → execute` when `hitl_enabled=true`

## What's Next (Phase 4)

- [x] User approved `.plan/phase-4-design.md` on 2026-06-13
- [x] Component 1: EvalConfig in settings — 7 new tests, 197 total green
- [x] Component 2: GoldenDataset + starter cases (5 cases in evals/golden/default.json) — 9 new tests
- [x] Component 3: Metrics factory (GEval/Faithfulness/Relevancy) — 8 new tests
- [x] Component 4: EvalRunner (run_case + run_dataset) — 7 new tests
- [x] Component 5: Langfuse score reporting (AgentTracer.log_score) — 2 new tests
- [x] Component 6: Golden eval test suite (tests/evals/, pytest -m eval) — 5 parametrized cases
- [x] Component 7: A/B comparison script (scripts/compare_evals.py) — manual

**Phase 4 complete — 223 unit+integration tests passing**

## Phase Completion Status

| Phase | Status |
|---|---|
| Phase 1 — Foundation | ✅ Complete — 90 tests green |
| Phase 2 — Reliability | ✅ Complete — 139 tests green |
| Phase 3 — Memory | ✅ Complete — 184 tests green |
| Phase 4 — Evals & Quality | ✅ Complete — 223 tests green |
| Phase 5 — Multi-agent | Not started |
| Phase 6 — Deployment & Triggers | Not started |
| Phase 7 — Auth & Security | Not started |

## Deferred

Manual Phase 2 verification (resume from checkpoint, HITL approval flow, budget exceeded demo) — deferred to after Phase 3. All automated tests pass.

## Blockers

None.

## Session Log

### 2026-06-13
- Defined project vision, phases, tech stack
- Settled Python over TypeScript (runs as microservice, language-agnostic to consumer)
- Settled LangGraph over Pydantic AI (more mature, built-in checkpointing and HITL)
- Added guardrails, HITL, structured outputs, prompt versioning, multi-tenancy, context window management, streaming, cost attribution to phases
- Established design-first working methodology
