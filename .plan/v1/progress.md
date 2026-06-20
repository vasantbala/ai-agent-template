# Progress

## Current Status

**Phase:** Phase 8 complete — all 8 phases done  
**Last updated:** 2026-06-14

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

## What's Next (Phase 5)

- [x] User approved `.plan/phase-5-design.md` on 2026-06-14
- [x] Component 1: SubAgentConfig in settings — 6 new tests, 50 config tests green
- [x] Component 2: SubAgentClient — 8 tests green
- [x] Component 3: AgentRegistry — 12 tests green
- [x] Component 4: Wire into execute + graph + API — 4 new routing tests; 253 total green

**Phase 5 complete — 253 unit+integration tests passing**

## Phase 8 (Demo UI)

- [x] Component 1: POST /v1/kb/seed endpoint — 8 tests green
- [x] Component 2: Gradio app (demo/app.py) — streaming chat, KB seeder tab, health check
- [x] Component 3: Docker Compose overlay (docker-compose.demo.yml) — demo service on port 7860
- [x] Component 4: Docs updated — Gradio section added to both example walkthroughs

**Phase 8 complete — demo accessible at http://localhost:7860 via overlay**

---

## What's Next (Phase 6)

- [x] Component 1: CostConfig + ScheduleConfig in settings — 63 config tests green
- [x] Component 2: cost_usd in AgentState + reason node + AgentResponse + Langfuse score — 263 unit tests green
- [x] Component 3: Streaming endpoint POST /v1/agent/stream (SSE) — 6 new tests, 269 unit tests green
- [x] Component 4: Webhook trigger POST /v1/triggers/webhook (202 + BackgroundTask) — 9 new tests, 278 unit tests green
- [x] Component 5: Scheduled runs via APScheduler AsyncIOScheduler — 6 new tests, 284 unit tests green

**Phase 6 complete — 284 unit tests passing**

## What's Next (Phase 7)

- [x] Component 1: AuthConfig + PiiConfig + AuditConfig + allowed_tools in settings — 85 config tests green
- [x] Component 2: API key + JWT middleware, applied to all /v1/ routes — 11 auth tests green
- [x] Component 3: PII scrubber (regex patterns), applied to input + output — 10 PII tests green
- [x] Component 4: ToolPermissionGuard allowlist, enforced in execute node — 8 permission tests green
- [x] Component 5+6: AuditLogger (tool_call + llm_decision events) wired into graph closures — 8 audit tests green
- [x] Component 7: prompts/v2/system.md scaffolded; compare_evals.py now runs — deferred bug fixed

**Phase 7 complete — 343 unit tests passing**

## Phase Completion Status

| Phase | Status |
|---|---|
| Phase 1 — Foundation | ✅ Complete — 90 tests green |
| Phase 2 — Reliability | ✅ Complete — 139 tests green |
| Phase 3 — Memory | ✅ Complete — 184 tests green |
| Phase 4 — Evals & Quality | ✅ Complete — 223 tests green |
| Phase 5 — Multi-agent | ✅ Complete — 253 tests green |
| Phase 6 — Deployment & Triggers | ✅ Complete — 284 tests green |
| Phase 7 — Auth & Security | ✅ Complete — 343 tests green |
| Phase 8 — Demo UI | ✅ Complete — Gradio UI, Docker overlay, docs updated |

## Deferred

- Manual Phase 2 verification (resume from checkpoint, HITL approval flow, budget exceeded demo)
- Phase 4 eval suite intermittent: GEval step-generation LLM call returns empty content on some runs (LiteLLM "Provider List" warning). Mitigation in place (`evaluation_steps` pre-specified, `_extract_json` extractor). No further action planned.

## Blockers

None.

## Session Log

### 2026-06-13
- Defined project vision, phases, tech stack
- Settled Python over TypeScript (runs as microservice, language-agnostic to consumer)
- Settled LangGraph over Pydantic AI (more mature, built-in checkpointing and HITL)
- Added guardrails, HITL, structured outputs, prompt versioning, multi-tenancy, context window management, streaming, cost attribution to phases
- Established design-first working methodology
