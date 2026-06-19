from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config.settings import MemoryConfig
from memory.store import Memory, MemoryStore, _build_filter


def make_config(**kwargs) -> MemoryConfig:
    return MemoryConfig(**{"qdrant_url": "http://localhost:6333", **kwargs})


def make_embedder(vector: list[float] | None = None) -> MagicMock:
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=vector or [0.1, 0.2, 0.3])
    return embedder


def make_search_result(text: str, score: float = 0.9) -> MagicMock:
    r = MagicMock()
    r.payload = {"text": text}
    r.score = score
    return r


def make_query_result(points: list) -> MagicMock:
    result = MagicMock()
    result.points = points
    return result


class TestMemory:
    def test_created_at_auto_populated(self):
        m = Memory(text="hello", tenant_id="t1", session_id="s1")
        assert m.created_at != ""

    def test_created_at_preserved_when_set(self):
        m = Memory(text="hello", tenant_id="t1", session_id="s1", created_at="2026-01-01T00:00:00+00:00")
        assert m.created_at == "2026-01-01T00:00:00+00:00"


class TestBuildFilter:
    def test_global_scope_returns_none(self):
        f = _build_filter("global", "tenant1", None, None)
        assert f is None

    def test_tenant_scope_filters_by_tenant(self):
        f = _build_filter("tenant", "acme", None, None)
        assert f is not None
        keys = [c.key for c in f.must]
        assert "tenant_id" in keys
        assert "session_id" not in keys

    def test_user_scope_filters_by_tenant_and_user(self):
        f = _build_filter("user", "acme", None, "user-42")
        keys = [c.key for c in f.must]
        assert "tenant_id" in keys
        assert "user_id" in keys

    def test_session_scope_filters_by_tenant_and_session(self):
        f = _build_filter("session", "acme", "sess-1", None)
        keys = [c.key for c in f.must]
        assert "tenant_id" in keys
        assert "session_id" in keys

    def test_user_scope_without_user_id_omits_user_filter(self):
        f = _build_filter("user", "acme", None, None)
        keys = [c.key for c in f.must]
        assert "user_id" not in keys


class TestMemoryStore:
    def make_store(self, config: MemoryConfig | None = None, vector: list[float] | None = None):
        cfg = config or make_config()
        embedder = make_embedder(vector)
        store = MemoryStore(cfg, embedder)
        store._client = MagicMock()
        store._client.get_collections = AsyncMock()
        store._client.create_collection = AsyncMock()
        store._client.upsert = AsyncMock()
        store._client.query_points = AsyncMock(return_value=make_query_result([]))
        return store, embedder

    async def test_ensure_collection_creates_when_missing(self):
        store, _ = self.make_store()
        collections_resp = MagicMock()
        collections_resp.collections = []
        store._client.get_collections.return_value = collections_resp

        await store.ensure_collection(dimensions=1536)
        store._client.create_collection.assert_awaited_once()

    async def test_ensure_collection_skips_when_exists(self):
        store, _ = self.make_store()
        existing = MagicMock()
        existing.name = "agent_memories"
        collections_resp = MagicMock()
        collections_resp.collections = [existing]
        store._client.get_collections.return_value = collections_resp

        await store.ensure_collection()
        store._client.create_collection.assert_not_awaited()

    async def test_store_embeds_and_upserts(self):
        vector = [0.1, 0.2, 0.3]
        store, embedder = self.make_store(vector=vector)
        mem = Memory(text="The capital of France is Paris.", tenant_id="t1", session_id="s1")

        await store.store(mem)

        embedder.embed.assert_awaited_once_with("The capital of France is Paris.")
        store._client.upsert.assert_awaited_once()
        point = store._client.upsert.call_args.kwargs["points"][0]
        assert point.vector == vector
        assert point.payload["text"] == "The capital of France is Paris."
        assert point.payload["tenant_id"] == "t1"

    async def test_retrieve_returns_text_list(self):
        store, embedder = self.make_store()
        store._client.query_points.return_value = make_query_result([
            make_search_result("Paris is the capital."),
            make_search_result("France is in Europe."),
        ])

        results = await store.retrieve("capital of France", "t1", "user", top_k=5)

        assert results == ["Paris is the capital.", "France is in Europe."]
        embedder.embed.assert_awaited_once_with("capital of France")

    async def test_retrieve_passes_top_k(self):
        store, _ = self.make_store()
        store._client.query_points.return_value = make_query_result([])

        await store.retrieve("query", "t1", "global", top_k=3)

        assert store._client.query_points.call_args.kwargs["limit"] == 3

    async def test_retrieve_returns_empty_list_when_no_results(self):
        store, _ = self.make_store()
        store._client.query_points.return_value = make_query_result([])

        results = await store.retrieve("query", "t1", "global")
        assert results == []

    async def test_retrieve_applies_scope_filter(self):
        store, _ = self.make_store()
        store._client.query_points.return_value = make_query_result([])

        await store.retrieve("query", "acme", "tenant", top_k=5)

        call_filter = store._client.query_points.call_args.kwargs["query_filter"]
        assert call_filter is not None
        keys = [c.key for c in call_filter.must]
        assert "tenant_id" in keys

    async def test_store_includes_user_id_in_payload(self):
        store, _ = self.make_store()
        mem = Memory(text="hello", tenant_id="t1", session_id="s1", user_id="user-42")

        await store.store(mem)

        point = store._client.upsert.call_args.kwargs["points"][0]
        assert point.payload["user_id"] == "user-42"

    async def test_user_scope_filter_includes_user_id(self):
        store, _ = self.make_store()
        store._client.query_points.return_value = make_query_result([])

        await store.retrieve("query", "acme", "user", user_id="user-42", top_k=5)

        call_filter = store._client.query_points.call_args.kwargs["query_filter"]
        keys = [c.key for c in call_filter.must]
        assert "user_id" in keys
        user_condition = next(c for c in call_filter.must if c.key == "user_id")
        assert user_condition.match.value == "user-42"

    async def test_different_users_get_different_filters(self):
        store, _ = self.make_store()
        store._client.query_points.return_value = make_query_result([])

        await store.retrieve("q", "acme", "user", user_id="alice", top_k=5)
        await store.retrieve("q", "acme", "user", user_id="bob", top_k=5)

        calls = store._client.query_points.await_args_list
        def get_user_id(call):
            f = call.kwargs["query_filter"]
            return next(c.match.value for c in f.must if c.key == "user_id")

        assert get_user_id(calls[0]) == "alice"
        assert get_user_id(calls[1]) == "bob"
