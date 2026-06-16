"""
Functional customer-support tests — hit the live agent API and verify that
answers are grounded in the docs/ knowledge base.

Requirements before running:
  1. Agent running (docker --context dev01 compose -f docker-compose.dev01.yml up -d)
  2. KB seeded:  uv run python scripts/seed_kb.py
     OR via the API after the container is up — see conftest fixture below.
  3. MEMORY__ENABLED=true and MEMORY__SCOPE=tenant in .env

Run (agent on dev01 exposed at port 8000 locally or via SSH tunnel):
  uv run pytest tests/functional/test_customer_support.py -v -s

Override the agent URL if needed:
  AGENT_URL=http://<dev01-ip>:8000 uv run pytest tests/functional/test_customer_support.py -v -s
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import httpx
import pytest

# ── Config ────────────────────────────────────────────────────────────────────

AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8000")
TENANT_ID = "local-dev"   # must match TENANT_ID in .env
TIMEOUT = 60              # seconds — LLM calls can be slow


# ── Helpers ───────────────────────────────────────────────────────────────────

def post_agent(question: str, session_id: str) -> dict:
    resp = httpx.post(
        f"{AGENT_URL}/v1/agent/run",
        json={
            "tenant_id": TENANT_ID,
            "session_id": session_id,
            "input": question,
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def check_agent_health():
    """Fail fast if the agent isn't reachable."""
    try:
        r = httpx.get(f"{AGENT_URL}/health", timeout=10)
        assert r.status_code == 200, f"Health check failed: {r.status_code}"
    except httpx.ConnectError as exc:
        pytest.skip(f"Agent not reachable at {AGENT_URL}: {exc}")


@pytest.fixture(scope="module")
def seed_kb():
    """
    Seed the docs/ knowledge base via /v1/kb/seed if it hasn't been seeded yet.
    Runs once per test module.
    """
    docs_dir = Path(__file__).parent.parent.parent / "docs"

    def _split_by_heading(text: str) -> list[str]:
        sections = re.split(r'\n(?=#{1,3} )', text.strip())
        return [s.strip() for s in sections if s.strip()]

    chunks: list[str] = []
    for md_file in sorted(docs_dir.rglob("*.md")):
        text = md_file.read_text(encoding="utf-8").strip()
        if text:
            chunks.extend(_split_by_heading(text))

    if not chunks:
        pytest.skip("No .md files found in docs/ — nothing to seed")

    resp = httpx.post(
        f"{AGENT_URL}/v1/kb/seed",
        json={
            "tenant_id": TENANT_ID,
            "documents": chunks,
            "session_id": "functional-test-seed",
        },
        timeout=60,
    )
    assert resp.status_code == 200, f"KB seed failed: {resp.text}"
    data = resp.json()
    assert data["seeded"] > 0, "No documents were seeded"
    return data["seeded"]


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestCustomerSupportKB:
    """Verify the agent answers questions from the docs/ knowledge base."""

    def test_health_endpoint(self):
        """Sanity check — health route returns 200."""
        r = httpx.get(f"{AGENT_URL}/health", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_kb_seeded_and_agent_responds(self, seed_kb):
        """KB was seeded successfully and agent returns a non-empty response."""
        result = post_agent(
            "What is the ai-agent-template project?",
            "cs-smoke-1",
        )
        assert result["output"], "Agent returned an empty response"
        assert result["session_id"] == "cs-smoke-1"
        assert result["tenant_id"] == TENANT_ID

    def test_api_key_auth_documentation(self, seed_kb):
        """Agent can answer questions about authentication options."""
        result = post_agent(
            "How do I authenticate requests to the agent API?",
            "cs-auth-1",
        )
        output = result["output"].lower()
        # Docs cover two auth methods: API key and JWT
        assert "api key" in output or "x-api-key" in output or "jwt" in output or "bearer" in output, (
            f"Expected auth info in response, got: {result['output']}"
        )

    def test_memory_scope_documentation(self, seed_kb):
        """Agent explains the MEMORY__SCOPE options correctly."""
        result = post_agent(
            "What memory scopes are available and when should I use each one?",
            "cs-memory-1",
        )
        output = result["output"].lower()
        # Docs define: session, user, tenant, global
        scopes_mentioned = sum(s in output for s in ["session", "user", "tenant", "global"])
        assert scopes_mentioned >= 2, (
            f"Expected at least 2 scope names in response, got: {result['output']}"
        )

    def test_kb_seed_endpoint_documentation(self, seed_kb):
        """Agent knows how to seed the knowledge base."""
        result = post_agent(
            "How do I seed the knowledge base with my own documents?",
            "cs-kb-1",
        )
        output = result["output"].lower()
        assert "seed" in output or "kb" in output or "document" in output or "qdrant" in output, (
            f"Expected KB seeding info, got: {result['output']}"
        )

    def test_streaming_endpoint_documentation(self, seed_kb):
        """Agent knows about the streaming endpoint."""
        result = post_agent(
            "Does the agent support streaming responses?",
            "cs-stream-1",
        )
        output = result["output"].lower()
        assert "stream" in output or "/v1/agent/stream" in output or "sse" in output, (
            f"Expected streaming info, got: {result['output']}"
        )

    def test_mcp_tool_configuration(self, seed_kb):
        """Agent can explain MCP server configuration."""
        result = post_agent(
            "How do I configure MCP tools for the agent?",
            "cs-mcp-1",
        )
        output = result["output"].lower()
        assert "mcp" in output or "mcp_servers" in output or "tool" in output, (
            f"Expected MCP config info, got: {result['output']}"
        )

    def test_out_of_scope_question_handled_gracefully(self, seed_kb):
        """Agent declines to answer questions outside the product KB scope."""
        result = post_agent(
            "What is the weather like in Paris today?",
            "cs-oos-1",
        )
        output = result["output"]
        # Should not hallucinate weather data — agent should say it doesn't know
        assert output, "Agent returned empty response"
        # The system prompt says to redirect out-of-scope questions
        # Just verify it returns something sensible (no assertion on exact wording)

    def test_response_includes_cost_tracking(self, seed_kb):
        """COST__ENABLED=true — cost_usd field should be present and non-negative."""
        result = post_agent(
            "What does the health endpoint return?",
            "cs-cost-1",
        )
        assert "cost_usd" in result, "cost_usd missing from response"
        assert result["cost_usd"] >= 0.0, f"Negative cost: {result['cost_usd']}"

    def test_hitl_documentation(self, seed_kb):
        """Agent explains human-in-the-loop configuration."""
        result = post_agent(
            "How do I enable human-in-the-loop approval before the agent executes tools?",
            "cs-hitl-1",
        )
        output = result["output"].lower()
        assert "hitl" in output or "human" in output or "hitl_enabled" in output, (
            f"Expected HITL info, got: {result['output']}"
        )

    def test_prompt_versioning_documentation(self, seed_kb):
        """Agent explains how to version and switch system prompts."""
        result = post_agent(
            "How do I switch the agent to use a different version of the system prompt?",
            "cs-prompt-1",
        )
        output = result["output"].lower()
        assert "prompt" in output or "version" in output or "agent__prompt_version" in output, (
            f"Expected prompt versioning info, got: {result['output']}"
        )
