from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from agent.state import AgentState
from config.settings import MemoryConfig
from memory.nodes import retrieve_memories


def make_state(**kwargs) -> AgentState:
    defaults = dict(tenant_id="t1", session_id="s1", messages=[])
    return AgentState(**{**defaults, **kwargs})


def make_store(memories: list[str] | None = None) -> MagicMock:
    store = MagicMock()
    store.retrieve = AsyncMock(return_value=memories or [])
    return store


def make_config(**kwargs) -> MemoryConfig:
    return MemoryConfig(**{"enabled": True, "scope": "user", "top_k": 5, **kwargs})


class TestRetrieveMemories:
    async def test_returns_empty_when_disabled(self):
        state = make_state(messages=[HumanMessage(content="hello")])
        store = make_store(["past memory"])
        config = make_config(enabled=False)

        result = await retrieve_memories(state, store, config)

        assert result == {}
        store.retrieve.assert_not_awaited()

    async def test_returns_empty_when_no_human_messages(self):
        state = make_state(messages=[AIMessage(content="I'm ready")])
        store = make_store(["past memory"])
        config = make_config()

        result = await retrieve_memories(state, store, config)
        assert result == {}

    async def test_returns_empty_when_no_memories_found(self):
        state = make_state(messages=[HumanMessage(content="what is the capital of France?")])
        store = make_store([])
        config = make_config()

        result = await retrieve_memories(state, store, config)
        assert result == {}

    async def test_injects_system_message_when_memories_found(self):
        state = make_state(messages=[HumanMessage(content="what is the capital of France?")])
        store = make_store(["Paris is the capital of France.", "France is in Western Europe."])
        config = make_config()

        result = await retrieve_memories(state, store, config)

        assert "messages" in result
        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert isinstance(msg, SystemMessage)
        assert "Paris is the capital of France." in msg.content
        assert "France is in Western Europe." in msg.content

    async def test_uses_last_human_message_as_query(self):
        state = make_state(messages=[
            HumanMessage(content="first question"),
            AIMessage(content="first answer"),
            HumanMessage(content="follow up question"),
        ])
        store = make_store([])
        config = make_config()

        await retrieve_memories(state, store, config)

        store.retrieve.assert_awaited_once()
        assert store.retrieve.call_args.kwargs["query"] == "follow up question"

    async def test_passes_tenant_id_and_session_id(self):
        state = make_state(
            tenant_id="acme",
            session_id="sess-99",
            messages=[HumanMessage(content="hello")],
        )
        store = make_store([])
        config = make_config()

        await retrieve_memories(state, store, config)

        call = store.retrieve.call_args.kwargs
        assert call["tenant_id"] == "acme"
        assert call["session_id"] == "sess-99"

    async def test_passes_scope_and_top_k_from_config(self):
        state = make_state(messages=[HumanMessage(content="hello")])
        store = make_store([])
        config = make_config(scope="tenant", top_k=3)

        await retrieve_memories(state, store, config)

        call = store.retrieve.call_args.kwargs
        assert call["scope"] == "tenant"
        assert call["top_k"] == 3

    async def test_memory_context_formatted_as_bullet_list(self):
        state = make_state(messages=[HumanMessage(content="hello")])
        store = make_store(["memory one", "memory two"])
        config = make_config()

        result = await retrieve_memories(state, store, config)

        content = result["messages"][0].content
        assert "- memory one" in content
        assert "- memory two" in content

    async def test_passes_user_id_from_state(self):
        state = make_state(user_id="user-42", messages=[HumanMessage(content="hello")])
        store = make_store([])
        config = make_config(scope="user")

        await retrieve_memories(state, store, config)

        assert store.retrieve.call_args.kwargs["user_id"] == "user-42"

    async def test_passes_none_user_id_when_not_set(self):
        state = make_state(user_id=None, messages=[HumanMessage(content="hello")])
        store = make_store([])
        config = make_config(scope="user")

        await retrieve_memories(state, store, config)

        assert store.retrieve.call_args.kwargs["user_id"] is None

    async def test_user_scope_with_user_id_isolates_per_user(self):
        # Two calls with different user_ids should pass different user_ids to store
        store = make_store([])
        config = make_config(scope="user")

        state_a = make_state(user_id="alice", messages=[HumanMessage(content="hello")])
        state_b = make_state(user_id="bob", messages=[HumanMessage(content="hello")])

        await retrieve_memories(state_a, store, config)
        await retrieve_memories(state_b, store, config)

        calls = store.retrieve.await_args_list
        assert calls[0].kwargs["user_id"] == "alice"
        assert calls[1].kwargs["user_id"] == "bob"
