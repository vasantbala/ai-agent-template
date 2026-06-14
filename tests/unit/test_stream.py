from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessageChunk

from api.routes.stream import _token_stream


def make_stream_event(content: str) -> dict:
    chunk = AIMessageChunk(content=content)
    return {"event": "on_chat_model_stream", "data": {"chunk": chunk}}


def make_non_stream_event() -> dict:
    return {"event": "on_chain_start", "data": {}}


async def _collect(gen) -> list[str]:
    result = []
    async for item in gen:
        result.append(item)
    return result


class TestTokenStream:
    async def test_emits_token_events(self):
        graph = MagicMock()
        graph.astream_events = MagicMock(return_value=_async_iter([
            make_stream_event("Hello"),
            make_stream_event(" world"),
        ]))

        events = await _collect(_token_stream(graph, {}, {}))

        token_events = [e for e in events if '"type": "token"' in e]
        assert len(token_events) == 2
        assert '"Hello"' in token_events[0]
        assert "world" in token_events[1]

    async def test_final_event_is_done(self):
        graph = MagicMock()
        graph.astream_events = MagicMock(return_value=_async_iter([
            make_stream_event("Paris"),
        ]))

        events = await _collect(_token_stream(graph, {}, {}))

        done_events = [e for e in events if '"type": "done"' in e]
        assert len(done_events) == 1
        payload = json.loads(done_events[0].removeprefix("data: ").strip())
        assert payload["output"] == "Paris"

    async def test_done_sentinel_terminates_stream(self):
        graph = MagicMock()
        graph.astream_events = MagicMock(return_value=_async_iter([
            make_stream_event("X"),
        ]))

        events = await _collect(_token_stream(graph, {}, {}))
        assert events[-1] == "data: [DONE]\n\n"

    async def test_non_stream_events_are_ignored(self):
        graph = MagicMock()
        graph.astream_events = MagicMock(return_value=_async_iter([
            make_non_stream_event(),
            make_stream_event("Hi"),
            make_non_stream_event(),
        ]))

        events = await _collect(_token_stream(graph, {}, {}))

        token_events = [e for e in events if '"type": "token"' in e]
        assert len(token_events) == 1

    async def test_done_output_concatenates_tokens(self):
        graph = MagicMock()
        graph.astream_events = MagicMock(return_value=_async_iter([
            make_stream_event("A"),
            make_stream_event("B"),
            make_stream_event("C"),
        ]))

        events = await _collect(_token_stream(graph, {}, {}))

        done_events = [e for e in events if '"type": "done"' in e]
        payload = json.loads(done_events[0].removeprefix("data: ").strip())
        assert payload["output"] == "ABC"

    async def test_empty_stream_produces_done_and_sentinel(self):
        graph = MagicMock()
        graph.astream_events = MagicMock(return_value=_async_iter([]))

        events = await _collect(_token_stream(graph, {}, {}))

        assert any('"type": "done"' in e for e in events)
        assert events[-1] == "data: [DONE]\n\n"


async def _async_iter(items):
    for item in items:
        yield item
