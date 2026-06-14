# Phase 7 Design — Auth & Security

**Status:** DRAFT — awaiting user approval before any code is written  
**Goal:** Harden the agent for shared or sensitive environments: authenticate callers, scrub PII, scope tool access, and produce a tamper-evident audit trail.

---

## What Phase 7 Delivers

- **API key auth** — all `/v1/` routes require a valid `X-API-Key` header; missing/invalid keys → 401
- **JWT auth** — optional alongside API keys; `Authorization: Bearer <token>` validated against a configured secret
- **PII scrubbing** — regex-based scrubber applied to inputs before the agent sees them and to outputs before they leave the service; configurable pattern set
- **Per-tool permission scoping** — `allowed_tools` allowlist in agent config; any tool call not on the list is blocked before execution
- **Audit log** — structured JSON event written for every tool call and every LLM decision; appended to a configurable file and echoed to stdout

---

## What We're NOT Building

- OAuth2 / OIDC / federated identity — API keys + JWT cover the .NET/server-to-server case
- NeMo Guardrails / LlamaGuard — heavy ML deps; out of scope for a template
- Vault / AWS Secrets Manager — env vars remain the secret store; the hooks are obvious for later
- Per-tenant key management — one key set for the whole service; per-tenant scoping is Phase 8+

---

## Directory Changes

```
src/
  auth/
    __init__.py
    middleware.py      # FastAPI dependency: validate API key or JWT
    config.py          # AuthConfig (moved here from settings for clarity, re-exported)
  security/
    __init__.py
    pii.py             # PiiScrubber — regex-based pattern matching + redaction
    permissions.py     # ToolPermissionGuard — allowlist check
  audit/
    __init__.py
    logger.py          # AuditLogger — structured JSON events
tests/
  unit/
    test_auth.py
    test_pii.py
    test_permissions.py
    test_audit.py
```

---

## Settings Changes

```python
class AuthConfig(BaseModel):
    enabled: bool = False
    api_keys: list[str] = []        # valid keys; empty list = all keys rejected when enabled
    jwt_secret: str | None = None   # when set, Bearer tokens are also accepted
    jwt_algorithm: str = "HS256"

class PiiConfig(BaseModel):
    enabled: bool = False
    # Which pattern groups to apply — add/remove without touching code
    patterns: list[Literal["email", "phone", "ssn", "credit_card", "ip_address"]] = [
        "email", "phone", "ssn", "credit_card"
    ]
    replacement: str = "[REDACTED]"

class Settings(BaseSettings):
    ...
    auth: AuthConfig = AuthConfig()
    pii: PiiConfig = PiiConfig()
    # agent.allowed_tools: list[str] = []  (added to existing AgentConfig)
```

`.env.example` additions:
```
# ── Auth ──────────────────────────────────────────────────────────────────────
# AUTH__ENABLED=true
# AUTH__API_KEYS='["sk-agent-abc123", "sk-agent-def456"]'
# AUTH__JWT_SECRET=change-me-in-production
# AUTH__JWT_ALGORITHM=HS256

# ── PII Scrubbing ─────────────────────────────────────────────────────────────
# PII__ENABLED=false
# PII__PATTERNS='["email","phone","ssn","credit_card"]'
# PII__REPLACEMENT=[REDACTED]

# ── Tool Permissions ──────────────────────────────────────────────────────────
# AGENT__ALLOWED_TOOLS='["read_file","search"]'  # empty = all tools allowed
```

---

## Component Designs

### 1. AuthConfig in settings + API key middleware (`src/auth/middleware.py`)

FastAPI `Security` dependency injected globally on all `/v1/` routes.

```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

async def require_auth(
    api_key: str | None = Security(api_key_header),
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    request: Request = ...,
) -> None:
    settings = request.app.state.settings
    if not settings.auth.enabled:
        return   # auth disabled — let everything through

    # Try API key first
    if api_key and api_key in settings.auth.api_keys:
        return

    # Try JWT if a secret is configured
    if credentials and settings.auth.jwt_secret:
        try:
            from jose import jwt
            jwt.decode(credentials.credentials, settings.auth.jwt_secret,
                       algorithms=[settings.auth.jwt_algorithm])
            return
        except Exception:
            pass

    raise HTTPException(status_code=401, detail="Invalid or missing credentials")
```

Applied in `create_app()`:
```python
from fastapi import Depends
app.include_router(agent_router, dependencies=[Depends(require_auth)])
app.include_router(stream_router, dependencies=[Depends(require_auth)])
app.include_router(webhook_router, dependencies=[Depends(require_auth)])
```

Health router is **not** protected (uptime checks must not require a key).

**Tests**: valid key passes, unknown key → 401, auth disabled → always passes, valid JWT passes, expired JWT → 401.

---

### 2. PII scrubber (`src/security/pii.py`)

Regex-based; runs on the raw input string before it enters the agent and on the final output string before it leaves.

```python
import re

_PATTERNS = {
    "email":       r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    "phone":       r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ssn":         r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d[ -]?){13,16}\b",
    "ip_address":  r"\b\d{1,3}(?:\.\d{1,3}){3}\b",
}

class PiiScrubber:
    def __init__(self, config: PiiConfig) -> None:
        active = {k: re.compile(v) for k, v in _PATTERNS.items() if k in config.patterns}
        self._patterns = active
        self._replacement = config.replacement
        self._enabled = config.enabled

    def scrub(self, text: str) -> str:
        if not self._enabled:
            return text
        for pattern in self._patterns.values():
            text = pattern.sub(self._replacement, text)
        return text
```

Applied in the `/v1/agent/run` and `/v1/agent/stream` routes:
```python
body_input = app_state.pii_scrubber.scrub(body.input)   # before agent sees it
output = app_state.pii_scrubber.scrub(output)            # before response leaves
```

`pii_scrubber` is created in lifespan and stored on `app.state`.

**Tests**: each pattern type is scrubbed, disabled scrubber is a no-op, multiple patterns in one string, replacement token is configurable.

---

### 3. Per-tool permission scoping (`src/security/permissions.py`)

Add `allowed_tools: list[str] = []` to existing `AgentConfig` (empty = allow all). Check in the execute node before any tool dispatch.

```python
class ToolPermissionGuard:
    def __init__(self, allowed_tools: list[str]) -> None:
        self._allowed = set(allowed_tools)  # empty set = allow all

    def check(self, tool_name: str) -> None:
        if self._allowed and tool_name not in self._allowed:
            raise PermissionError(f"Tool '{tool_name}' is not in the allowed_tools list")
```

Wired into `execute` node:
```python
if permission_guard:
    permission_guard.check(task.tool_name)
```

`build_graph` receives a `permission_guard` constructed from `agent_config.allowed_tools`.

**Tests**: tool in allowlist passes, tool not in allowlist → PermissionError, empty allowlist allows all, guard is None when allowlist is empty.

---

### 4. Audit logger (`src/audit/logger.py`)

One JSON line per event, written to `audit.log` (or configured path) and echoed to the `audit` Python logger.

```python
import json, logging
from datetime import datetime, UTC

_log = logging.getLogger("audit")

class AuditLogger:
    def __init__(self, path: str | None = "audit.log") -> None:
        self._path = path

    def _emit(self, event: dict) -> None:
        line = json.dumps({"ts": datetime.now(UTC).isoformat(), **event})
        _log.info(line)
        if self._path:
            with open(self._path, "a") as f:
                f.write(line + "\n")

    def tool_call(self, session_id: str, tenant_id: str, tool_name: str,
                  args: dict, result: str, success: bool) -> None:
        self._emit({"event": "tool_call", "session_id": session_id,
                    "tenant_id": tenant_id, "tool_name": tool_name,
                    "args": args, "result_preview": result[:200], "success": success})

    def llm_decision(self, session_id: str, tenant_id: str, iteration: int,
                     tool_calls: list[str]) -> None:
        self._emit({"event": "llm_decision", "session_id": session_id,
                    "tenant_id": tenant_id, "iteration": iteration,
                    "tool_calls": tool_calls})
```

`AuditLogger` is created in lifespan, stored on `app.state`, threaded into the execute node (tool_call) and reason node (llm_decision).

`AuditConfig` (new settings block):
```python
class AuditConfig(BaseModel):
    enabled: bool = False
    log_path: str = "audit.log"   # set to "" to disable file output, keep stdout
```

**Tests**: tool_call event written with correct fields, llm_decision event written, disabled logger writes nothing, result truncated to 200 chars.

---

### 5. Deferred fix: compare_evals.py v2 prompt

The `compare_evals.py` script fails when no `prompts/v2/system.md` exists. Fix: scaffold `prompts/v2/system.md` as a copy of v1, so the script runs against an actual alternative. This unblocks the A/B eval workflow from Phase 4.

---

## API Response — no changes

No new fields in `AgentResponse`. Auth failures return 401 before the agent runs. PII scrubbing is invisible to the caller (the scrubbed output is the response).

---

## Build Order

| # | Component | Files | Tests |
|---|---|---|---|
| 1 | AuthConfig + PiiConfig + AuditConfig in settings | `src/config/settings.py` | `test_config.py` (extend) |
| 2 | API key + JWT middleware | `src/auth/middleware.py` | `test_auth.py` |
| 3 | PII scrubber | `src/security/pii.py` | `test_pii.py` |
| 4 | Per-tool permission scoping | `src/security/permissions.py`, extend `execute.py` + `graph.py` + `AgentConfig` | `test_permissions.py` |
| 5 | Audit logger | `src/audit/logger.py` | `test_audit.py` |
| 6 | Wire auth + PII + audit into API routes | `src/api/routes/agent.py`, `stream.py`, `main.py` | extend integration tests |
| 7 | Fix compare_evals.py (scaffold prompts/v2/) | `prompts/v2/system.md`, `scripts/compare_evals.py` | manual |

---

## Definition of Done for Phase 7

- [ ] All unit tests pass (`pytest tests/unit/`)
- [ ] `POST /v1/agent/run` returns 401 when auth is enabled and key is missing
- [ ] Valid `X-API-Key` passes; valid JWT passes
- [ ] Health endpoint is not gated by auth
- [ ] PII patterns are scrubbed from input and output when `PII__ENABLED=true`
- [ ] Tool call blocked with 500 when not in `allowed_tools`
- [ ] `audit.log` contains one JSON line per tool call and LLM decision
- [ ] `compare_evals.py` runs without error when `prompts/v2/system.md` exists
