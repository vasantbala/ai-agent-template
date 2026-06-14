from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.webhook import router, WebhookRequest


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    from config.prompts import PromptManager
    from agent.graph import AgentState

    mock_prompts = MagicMock(spec=PromptManager)
    mock_prompts.get_system_prompt.return_value = "You are a helpful assistant."

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value={
        "tenant_id": "t1",
        "session_id": "s1",
        "messages": [],
        "tasks": [],
        "current_task_index": 0,
        "iteration": 1,
        "tokens_used": 0,
        "cost_usd": 0.0,
        "error": None,
    })

    app.state.prompts = mock_prompts
    app.state.graph = mock_graph
    return app


class TestWebhookRoute:
    def test_returns_202(self):
        client = TestClient(make_app())
        response = client.post("/v1/triggers/webhook", json={
            "tenant_id": "acme",
            "input": "Run the daily report",
        })
        assert response.status_code == 202

    def test_response_has_accepted_true(self):
        client = TestClient(make_app())
        response = client.post("/v1/triggers/webhook", json={
            "tenant_id": "acme",
            "input": "Do something",
        })
        data = response.json()
        assert data["accepted"] is True

    def test_response_has_session_id(self):
        client = TestClient(make_app())
        response = client.post("/v1/triggers/webhook", json={
            "tenant_id": "acme",
            "input": "Do something",
        })
        data = response.json()
        assert "session_id" in data
        assert data["session_id"]

    def test_uses_provided_session_id(self):
        client = TestClient(make_app())
        response = client.post("/v1/triggers/webhook", json={
            "tenant_id": "acme",
            "input": "task",
            "session_id": "my-session-123",
        })
        assert response.json()["session_id"] == "my-session-123"

    def test_generates_session_id_when_not_provided(self):
        client = TestClient(make_app())
        response = client.post("/v1/triggers/webhook", json={
            "tenant_id": "acme",
            "input": "task",
        })
        session_id = response.json()["session_id"]
        assert session_id.startswith("wh-")

    def test_missing_tenant_id_returns_422(self):
        client = TestClient(make_app())
        response = client.post("/v1/triggers/webhook", json={"input": "task"})
        assert response.status_code == 422

    def test_missing_input_returns_422(self):
        client = TestClient(make_app())
        response = client.post("/v1/triggers/webhook", json={"tenant_id": "acme"})
        assert response.status_code == 422


class TestWebhookRequest:
    def test_session_id_optional(self):
        req = WebhookRequest(tenant_id="t1", input="hello")
        assert req.session_id is None

    def test_user_id_optional(self):
        req = WebhookRequest(tenant_id="t1", input="hello")
        assert req.user_id is None
