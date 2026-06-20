# Design Retrospective: AI Agent Template

## Context

After a debugging session to make the multi-agent research pipeline work end-to-end, we found and fixed a significant number of bugs. The question is: is this still a sound base for building production agents, what are its real limitations, and which of those can be fixed by design changes?

---

## Bugs Fixed (Were Showstoppers, Now Resolved)

These were real breakages that prevented the system from working at all — not design limitations:

| Bug | Fix |
|---|---|
| Tool schema in Anthropic format (`input_schema`) instead of OpenAI (`parameters`) | `src/agent/registry.py` — rebuilt to OpenAI format |
| `tool_call_id` not propagated from LLM response to `ToolMessage` | `src/agent/state.py` + `execute.py` + `reason.py` |
| `AIMessage` built without `tool_calls` list → provider rejected conversation history | `reason.py` — now builds `lc_tool_calls` and attaches to AIMessage |
| All LangChain messages passed as objects; LiteLLM expected OpenAI dicts | `src/llm/client.py` — added `_to_openai_dict()` converter |
| `tool_choice='auto'` — model answered from training data, never called tools | `reason.py` — iter-0 forces search tool (or `required`), iter-N uses `auto` |
| `LANGFUSE__ENABLED` defaulted to `false`; tracing silently disabled | Documented; add `LANGFUSE__ENABLED=true` to env |
| Current date not injected → model dismissed 2026 search results as "future-dated" | `src/config/prompts.py` — prepends `Today's date is ...` at load time |
| `AGENT__ALLOWED_TOOLS` listed `brave_search` but MCP exposes `brave_web_search` | `.env.researcher` corrected |
| Researcher URL in `.env.parent` pointed at host port 8001, not container port 8000 | `.env.parent` corrected |
| `mcp-server-fetch` package name wrong on npm; it's a Python package | `.env.researcher` uses `uv tool run mcp-server-fetch` |

**Verdict on these:** Fixable bugs, not design flaws. The core architecture survives them.

---

## Real Limitations

### Tier 1 — Immediately Fixable by Design Changes

**1. Memory poisoning + cross-session privacy leakage**
- After each run, the last AI message is stored as a memory. Wrong answers get stored and retrieved in future sessions, overriding live search results. More critically, with scope=`user` or `tenant`, one user's memories can surface in another user's session — a privacy/PII risk.
- Two specific holes:
  - **Tenant isolation not enforced at memory retrieval** — `tenant_id` comes from the request body (not JWT), so a user can craft a request with another tenant's ID and access their memories. (See item 4.)
  - **Scope misconfiguration risk** — if scope is set to `tenant` to share a knowledge base, personal session data stored under the same collection is also exposed to all users in that tenant.
- **Fix (poisoning):** Store `{query, tool_name, raw_result_excerpt}` rather than the LLM synthesis. Memory becomes a cache of tool results, not hallucinations.
- **Fix (privacy):** Validate `tenant_id` from JWT (item 4). Separate personal memory (scope=user) from shared knowledge bases (scope=tenant) into distinct Qdrant collections — don't use the same collection with a scope flag.
- **Note on session persistence:** Scoping to `session_id` alone would lose cross-session memory entirely. The right model is to persist `session_id` as a long-lived client token (like NotebookLM does), treat it as a credential, and scope retrieval to `{tenant_id, user_id, session_id}` for personal context.

**2. No memory TTL or overwrite**
- Stale memories accumulate forever. There is no update-in-place or expiry.
- **Fix:** Add an `expires_at` field and a filter in `retrieve_memories`. Topic-keyed upsert (same factual question replaces its prior answer) handles the update case. TTL handles the age-out case — factual lookups (current events, prices) should expire in days; preference/biographical memories can be longer-lived.

**3. Sequential tool execution**
- `execute.py` handles one task at a time (`current_task_index`). If the LLM returns 3 tool calls in one turn, they execute serially.
- **Fix:** Batch all pending tasks in one `asyncio.gather()` call. The state graph already collects tasks as a list; the execute node just needs to be parallelized.

**4. Tenant isolation not enforced**
- `tenant_id` comes from the request body. An authenticated user can send any `tenant_id` and access another tenant's memories. JWT claims are validated for signature only — no claim-to-tenant binding.
- **Fix:** Extract `tenant_id` from JWT claims in the auth middleware; ignore the body value.

**5. Sub-agents called without auth**
- `SubAgentClient` POSTs to `http://researcher:8000/v1/agent/run` with no API key. If the researcher ever gets network exposure, it's unprotected.
- **Fix:** Pass `AGENT_API_KEY` env var to sub-agent configs and include it as `X-API-Key` in `SubAgentClient.call()`.

**6. `tool_choice` logic is heuristic and brittle**
- Currently: "if any tool name contains 'search', force that tool on iter 0." This breaks if an agent has a search tool and a lookup tool and the question calls for lookup first.
- **Fix:** Replace the name-based heuristic with explicit per-agent config: `AGENT__FIRST_TOOL=brave_web_search`. Or use a planning prompt step (iter 0 = plan only, iter 1+ = execute).

### Tier 2 — Fixable But Require More Refactoring

**7. SQLite checkpointer not distributed-ready**
- `checkpoints.db` is a local file. Two API replicas would fight over it.
- **Fix:** LangGraph ships a PostgreSQL checkpointer (`AsyncPostgresSaver`). Swap it in `graph.py`; no other changes needed. But requires Postgres in the infra stack.

**8. Single Qdrant instance, no abstraction**
- `MemoryStore` is directly coupled to `AsyncQdrantClient`. No interface to swap backends.
- **Fix:** Extract a `MemoryBackend` protocol with `store()` / `retrieve()` methods. Ship a Qdrant implementation and optionally a Postgres pgvector one.

**9. Embedding dimensions hardcoded to 1536**
- Changing the embedding model (e.g. to a 3072-dim model) requires re-creating the Qdrant collection and re-embedding all memories.
- **Fix:** Make dimension configurable in settings; auto-create collection with correct dims at startup. Add a migration step.

**10. Audit log on the critical path**
- Audit events are written synchronously to `audit.log`. High throughput = I/O bottleneck.
- **Fix:** Queue audit writes to a background `asyncio.Queue` and drain it in a background task.

### Tier 3 — Fundamental Architecture Tradeoffs (Not Easily Changed)

**11. Linear graph: reason → execute → reason**
- Good for: predictable single-topic agents, debugging, HITL gates.
- Bad for: agents that need to branch, run parallel sub-plans, or maintain multiple concurrent goals.
- **Mitigation:** Not worth changing the base pattern. For complex orchestration, use a planner-executor split (two separate agents, planner emits a task list, executor runs it).

**12. Memory is RAG on LLM outputs, not facts**
- Storing the AI's summarised answer as a memory means you're doing RAG on generated text, not ground truth. Hallucinated memories compound.
- **Mitigation:** This is a fundamental trade-off of the "summary memory" pattern. Fix is to store structured facts with provenance (tool name + raw result excerpt), not the LLM synthesis. Requires redesigning the memory write path.

**13. LiteLLM as the single abstraction layer**
- Works well for OpenAI-compatible providers. Breaks or degrades for providers with non-standard calling conventions.
- **Mitigation:** Already using `litellm.drop_params=True` to handle unsupported params. The OpenAI-format normalization in `_to_openai_dict()` is the right approach; just needs ongoing maintenance as providers evolve.
- **Claude specifically:** The tool schema fix (OpenAI format) does NOT break Claude. LiteLLM converts OpenAI-format schemas to Anthropic's native `input_schema` format before sending, and normalises the response back. The fix is more correct — the pre-fix Anthropic format only accidentally worked with Claude and would have broken any other provider.

**14. MCP server startup blocks API startup**
- MCP servers (`npx`, `uv tool run`) are launched as subprocesses at uvicorn startup. If an MCP server takes 10s to install packages (first run), the FastAPI app is not ready for traffic.
- **Mitigation:** Lazy-connect MCP servers on first tool call, not at startup. Circuit breaker already handles unavailability — just remove the startup blocking.

**15. Sub-agent communication protocol (future)**
- The current `SubAgentClient` (HTTP POST to `/v1/agent/run` with `call_` prefix routing) is a homegrown version of what Google's [Agent2Agent (A2A) protocol](https://google.github.io/A2A/) standardises: agent capability advertisement, task delegation, streaming, and inter-agent auth.
- Current Docker-based approach is sufficient for a homogeneous fleet on this template.
- **Future path:** Each agent exposes an A2A-compatible endpoint alongside `/v1/agent/run`. `SubAgentClient` gets an A2A transport option. Nothing in the graph or execute node changes — it's a transport swap. Worth tracking but no urgency while on a single Docker Compose stack.

---

## Is It Still a Good Base?

**Yes, with clear eyes about what it is.**

The template is excellent for:
- Single-tenant or small-team deployments
- Agent prototypes that need to go from zero to working quickly
- Showcasing the MCP + sub-agent pattern
- Evaluating whether LLM agents can solve a problem before investing in custom infra

It is not (yet) suitable as-is for:
- Multi-tenant SaaS (tenant isolation not enforced)
- Horizontally scaled deployments (SQLite checkpointer)
- Long-lived production agents where memory accuracy is critical (no TTL, poisoning risk)
- Latency-sensitive applications (sequential tool execution, sync audit log)

---

## Example Coverage Gap Analysis

The two existing examples (`single-agent-kb-qa.md`, `multi-agent-research.md`) cover the happy path for Phases 1, 3, 5, and 8. Four phases have zero walkthrough coverage.

### What the examples cover

| Feature | KB Q&A | Multi-agent Research |
|---|---|---|
| Basic agent run (`/v1/agent/run`) | ✅ | ✅ |
| Prompt versioning | ✅ | ✅ |
| Memory / Qdrant | ✅ (knowledge base) | ✅ (session memory) |
| MCP tools | — | ✅ (Brave Search + fetch) |
| Sub-agents | — | ✅ |
| Demo UI (Gradio) | ✅ | ✅ |
| Langfuse tracing | partial | ✅ |
| Docker Compose | ✅ | ✅ |

### What's built but has no example

**Phase 2 — Reliability** (completely dark)
- HITL approval flow — agent pauses mid-run for human approval before tool execution
- Circuit breaker — what happens when an MCP server starts failing
- Token budget — what happens when the agent hits `max_tokens_per_run`
- Context window summarization — long conversation behaviour
- Checkpoint resume — resuming an interrupted run (explicitly deferred in progress.md)

**Phase 4 — Evals** (completely dark)
- Running `pytest -m eval` against a golden dataset
- `scripts/compare_evals.py` for A/B model comparison
- Langfuse score reporting per run

**Phase 6 — Triggers** (mostly dark)
- `/v1/agent/stream` SSE streaming — KB Q&A mentions it but has no walkthrough
- `/v1/triggers/webhook` — no example
- Scheduled runs (`SCHEDULE__ENABLED`, cron) — mentioned in multi-agent doc but not demonstrated end-to-end

**Phase 7 — Auth & Security** (completely dark)
- API key authentication (`X-API-Key` header) — neither example enables auth
- JWT authentication (Bearer token)
- PII scrubbing — what gets masked, how to configure patterns
- Tool permission allowlist (`AGENT__ALLOWED_TOOLS`) — only appeared as a debugging fix, never explained
- Audit log

### Missing examples to write

| Example | Phases covered |
|---|---|
| `secure-deployment.md` | Phase 7 — API key + JWT auth, PII scrubber, tool allowlist, audit log |
| `eval-and-compare.md` | Phase 4 — golden dataset, running evals, A/B scoring in Langfuse |
| `streaming-and-webhooks.md` | Phase 6 — SSE streaming client, webhook trigger, scheduled digest |
| `reliability-and-hitl.md` | Phase 2 — HITL flow, circuit breaker demo, token budget, checkpoint resume |

---

## Recommended Next Design Changes (Priority Order)

1. **Parallel tool execution** in `execute.py` — highest value, low risk, purely additive
2. **Memory TTL + confidence flag** — prevents the class of bug we just spent hours debugging
3. **Tenant-to-JWT binding** in auth middleware — necessary before any multi-tenant use
4. **Sub-agent API key propagation** in `SubAgentClient` — security gap
5. **PostgreSQL checkpointer** (when scaling beyond single instance)
6. **Lazy MCP connection** (when startup time matters)
7. **Structured fact memory** (long-term; replaces summary memory pattern)
