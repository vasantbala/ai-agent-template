from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.kb import router
from config.settings import MemoryConfig


def make_app(memory_enabled: bool = True, store: MagicMock | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    mock_settings = MagicMock()
    mock_settings.memory = MemoryConfig(enabled=memory_enabled)

    mock_store = store or MagicMock()
    mock_store.store = AsyncMock()

    app.state.settings = mock_settings
    app.state.memory_store = mock_store if memory_enabled else None

    return app


class TestSeedEndpoint:
    def test_seeds_documents_returns_count(self):
        client = TestClient(make_app())
        response = client.post("/v1/kb/seed", json={
            "tenant_id": "acme",
            "documents": ["Doc one.", "Doc two.", "Doc three."],
        })
        assert response.status_code == 200
        assert response.json()["seeded"] == 3

    def test_store_called_once_per_document(self):
        mock_store = MagicMock()
        mock_store.store = AsyncMock()
        client = TestClient(make_app(store=mock_store))
        client.post("/v1/kb/seed", json={
            "tenant_id": "acme",
            "documents": ["A", "B"],
        })
        assert mock_store.store.await_count == 2

    def test_memory_disabled_returns_400(self):
        client = TestClient(make_app(memory_enabled=False))
        response = client.post("/v1/kb/seed", json={
            "tenant_id": "acme",
            "documents": ["Doc one."],
        })
        assert response.status_code == 400
        assert "MEMORY__ENABLED" in response.json()["detail"]

    def test_empty_documents_returns_zero(self):
        client = TestClient(make_app())
        response = client.post("/v1/kb/seed", json={
            "tenant_id": "acme",
            "documents": [],
        })
        assert response.status_code == 200
        assert response.json()["seeded"] == 0

    def test_blank_strings_are_filtered(self):
        mock_store = MagicMock()
        mock_store.store = AsyncMock()
        client = TestClient(make_app(store=mock_store))
        response = client.post("/v1/kb/seed", json={
            "tenant_id": "acme",
            "documents": ["Real doc.", "   ", ""],
        })
        assert response.json()["seeded"] == 1
        assert mock_store.store.await_count == 1

    def test_custom_session_id(self):
        mock_store = MagicMock()
        mock_store.store = AsyncMock()
        client = TestClient(make_app(store=mock_store))
        client.post("/v1/kb/seed", json={
            "tenant_id": "acme",
            "documents": ["Doc."],
            "session_id": "import-batch-001",
        })
        call_args = mock_store.store.call_args[0][0]
        assert call_args.session_id == "import-batch-001"

    def test_tenant_id_propagated_to_store(self):
        mock_store = MagicMock()
        mock_store.store = AsyncMock()
        client = TestClient(make_app(store=mock_store))
        client.post("/v1/kb/seed", json={
            "tenant_id": "my-tenant",
            "documents": ["Doc."],
        })
        call_args = mock_store.store.call_args[0][0]
        assert call_args.tenant_id == "my-tenant"

    def test_missing_tenant_id_returns_422(self):
        client = TestClient(make_app())
        response = client.post("/v1/kb/seed", json={"documents": ["Doc."]})
        assert response.status_code == 422
