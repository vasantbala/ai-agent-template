"""
AI Agent Demo UI
----------------
A Gradio interface for testing and showcasing the agent API.

Tabs:
  Chat      — real-time streaming conversation via /v1/agent/stream
  KB Seeder — seed documents into the knowledge base via /v1/kb/seed

Config sidebar sets the agent URL, tenant, user ID, and API key.
All state is local to the browser session — nothing is stored server-side.

Run standalone:
  pip install -r requirements.txt
  AGENT_URL=http://localhost:8000 python app.py

Run via Docker Compose:
  docker compose -f docker-compose.yml -f docker-compose.demo.yml up
"""
from __future__ import annotations

import json
import os
import uuid

import gradio as gr
import httpx

DEFAULT_AGENT_URL = os.environ.get("AGENT_URL", "http://localhost:8000")
DEFAULT_API_KEY = os.environ.get("AGENT_API_KEY", "")


# ── helpers ──────────────────────────────────────────────────────────────────

def _headers(api_key: str) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if api_key.strip():
        h["X-API-Key"] = api_key.strip()
    return h


def _new_session_id() -> str:
    return f"demo-{uuid.uuid4().hex[:12]}"


# ── chat ─────────────────────────────────────────────────────────────────────

async def chat(
    message: str,
    history: list[dict],
    agent_url: str,
    tenant_id: str,
    user_id: str,
    api_key: str,
    session_id: str,
) -> str:
    """Call /v1/agent/run and return the full response."""
    url = f"{agent_url.rstrip('/')}/v1/agent/run"
    body = {
        "tenant_id": tenant_id,
        "session_id": session_id,
        "user_id": user_id.strip() or None,
        "input": message,
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=_headers(api_key), json=body)
        if resp.status_code == 200:
            return resp.json().get("output", "")
        return f"[Error {resp.status_code}] {resp.text}"
    except httpx.ConnectError:
        return f"[Connection error] Could not reach agent at {agent_url}. Is it running?"
    except Exception as exc:
        return f"[Error] {exc}"


# ── kb seeder ─────────────────────────────────────────────────────────────────

def seed_kb(
    documents_text: str,
    tenant_id: str,
    api_key: str,
    agent_url: str,
    session_id: str,
) -> str:
    """POST documents to /v1/kb/seed and return a status message."""
    lines = [ln.strip() for ln in documents_text.splitlines() if ln.strip()]
    if not lines:
        return "No documents to seed — paste one document per line."

    url = f"{agent_url.rstrip('/')}/v1/kb/seed"
    body = {"tenant_id": tenant_id, "documents": lines, "session_id": session_id}

    try:
        resp = httpx.post(url, headers=_headers(api_key), json=body, timeout=30)
        if resp.status_code == 200:
            count = resp.json().get("seeded", 0)
            return f"✓ Seeded {count} document{'s' if count != 1 else ''} into tenant '{tenant_id}'."
        elif resp.status_code == 400:
            return f"✗ {resp.json().get('detail', 'Memory not enabled on the agent.')}"
        elif resp.status_code == 401:
            return "✗ Unauthorized — check the API key in the Config sidebar."
        else:
            return f"✗ Error {resp.status_code}: {resp.text}"
    except httpx.ConnectError:
        return f"✗ Could not reach agent at {agent_url}. Is it running?"
    except Exception as exc:
        return f"✗ {exc}"


# ── health check ──────────────────────────────────────────────────────────────

def check_health(agent_url: str) -> str:
    try:
        resp = httpx.get(f"{agent_url.rstrip('/')}/health", timeout=5)
        if resp.status_code == 200:
            return "● Agent reachable"
        return f"● Agent returned {resp.status_code}"
    except Exception:
        return "○ Agent unreachable"


# ── layout ────────────────────────────────────────────────────────────────────

with gr.Blocks(title="AI Agent Demo") as demo:
    gr.Markdown("# AI Agent Demo")

    with gr.Row():
        # ── sidebar ──────────────────────────────────────────────────────────
        with gr.Column(scale=1, min_width=260):
            gr.Markdown("### Config")

            agent_url = gr.Textbox(
                label="Agent URL",
                value=DEFAULT_AGENT_URL,
                placeholder="http://localhost:8000",
            )
            tenant_id = gr.Textbox(
                label="Tenant ID",
                value="local-dev",
                placeholder="local-dev",
            )
            user_id = gr.Textbox(
                label="User ID (optional)",
                value="",
                placeholder="alice",
            )
            api_key = gr.Textbox(
                label="API Key (optional)",
                value=DEFAULT_API_KEY,
                type="password",
                placeholder="sk-agent-...",
            )
            session_id = gr.Textbox(
                label="Session ID",
                value=_new_session_id(),
                interactive=False,
            )
            with gr.Row():
                new_session_btn = gr.Button("New session", size="sm")
                health_btn = gr.Button("Check agent", size="sm")
            health_status = gr.Markdown("○ Not checked")

            new_session_btn.click(
                fn=lambda: _new_session_id(),
                outputs=session_id,
            )
            health_btn.click(
                fn=check_health,
                inputs=[agent_url],
                outputs=health_status,
            )

        # ── main panel ───────────────────────────────────────────────────────
        with gr.Column(scale=3):
            with gr.Tabs():
                # Chat tab
                with gr.Tab("Chat"):
                    chatbot = gr.ChatInterface(
                        fn=chat,
                        additional_inputs=[
                            agent_url,
                            tenant_id,
                            user_id,
                            api_key,
                            session_id,
                        ],
                        examples=[
                            ["What can you help me with?"],
                            ["What is the return policy for annual plans?"],
                            ["Which plan includes API access?"],
                        ],
                    )

                # KB Seeder tab
                with gr.Tab("KB Seeder"):
                    gr.Markdown(
                        "Paste documents below — **one document per line**. "
                        "Each line is embedded and stored in Qdrant under the "
                        "configured tenant ID. Requires `MEMORY__ENABLED=true` "
                        "on the agent."
                    )
                    docs_input = gr.Textbox(
                        label="Documents",
                        lines=12,
                        placeholder=(
                            "Enterprise licenses support up to 50 seats and include priority support.\n"
                            "Annual plans include a 30-day money-back guarantee.\n"
                            "SSO via SAML 2.0 is available on Enterprise plans."
                        ),
                    )
                    seed_btn = gr.Button("Seed KB", variant="primary")
                    seed_status = gr.Markdown("")

                    seed_btn.click(
                        fn=seed_kb,
                        inputs=[docs_input, tenant_id, api_key, agent_url, session_id],
                        outputs=seed_status,
                    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        theme=gr.themes.Soft(),
    )
