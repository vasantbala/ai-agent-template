# AI Agent Template — Claude Working Guide

## Project Goal

A reusable, forkable Python microservice template for building production-grade AI agents. Consumed over HTTP/REST so any host product (web, .NET/Windows Forms, etc.) can integrate without caring about the internal language.

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python + uv |
| Agent framework | LangGraph |
| LLM interface | LiteLLM (OpenAI, OpenRouter, Anthropic) |
| MCP integration | Official Python MCP SDK |
| Config | Pydantic Settings |
| API layer | FastAPI |
| Observability | Langfuse |
| Vector store | Qdrant |
| Guardrails | Guardrails AI |
| Evals | DeepEval |
| Auth | API keys + JWT (Phase 7) |
| Containers | Docker + Docker Compose |
| Tests | pytest |

Full rationale: `.plan/initial-idea.md`

## Project Structure (evolves as phases complete)

```
.plan/                  # Design docs — read before coding
  initial-idea.md       # Vision, tech stack, all phases
  decisions.md          # Non-obvious decisions and rationale
  progress.md           # Current state — always read this first
  phase-1-design.md     # Phase 1 detailed design (write before coding)
  phase-N-design.md     # One per phase
src/                    # Agent source code
tests/                  # pytest test suite
docker-compose.yml      # Local dev environment
CLAUDE.md               # This file
```

## Standing Rules — Follow These Every Session

### Before writing any code
1. Read `.plan/progress.md` to understand current state
2. Read the relevant `.plan/phase-N-design.md` for the phase in progress
3. Do not write code for a phase until its design doc exists and the user has explicitly approved it

### While coding
- Build one component at a time — each must have tests and pass before moving to the next
- Commit after each green component with a clear message
- If a design decision arises that isn't in the design doc, surface it to the user before proceeding

### Before ending any session
- Update `.plan/progress.md` with: what was completed, what is in flight, what is next, and any blockers

### General
- No code without a design doc. No exceptions.
- When in doubt about scope, re-read the phase design doc rather than improvising
- Keep code small and testable — one interface or component per logical unit
