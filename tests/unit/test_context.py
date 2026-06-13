from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from reliability.context import ContextManager, _estimate_tokens


def make_llm(summary: str = "A summary.") -> MagicMock:
    llm = MagicMock()
    response = MagicMock()
    response.choices[0].message.content = summary
    llm.complete = AsyncMock(return_value=response)
    return llm


class TestEstimateTokens:
    def test_empty_returns_zero(self):
        assert _estimate_tokens([]) == 0

    def test_approximates_chars_over_four(self):
        msg = HumanMessage(content="a" * 400)
        assert _estimate_tokens([msg]) == 100

    def test_accumulates_across_messages(self):
        msgs = [HumanMessage(content="a" * 200), AIMessage(content="b" * 200)]
        assert _estimate_tokens(msgs) == 100


class TestContextManager:
    async def test_returns_unchanged_when_under_threshold(self):
        llm = make_llm()
        cm = ContextManager(llm, threshold_tokens=10_000)
        msgs = [SystemMessage(content="sys"), HumanMessage(content="hello")]
        result = await cm.maybe_summarise(msgs)
        assert result == msgs
        llm.complete.assert_not_awaited()

    async def test_summarises_when_over_threshold(self):
        llm = make_llm("The user asked about math.")
        cm = ContextManager(llm, threshold_tokens=1, preserve_last_n=1)
        msgs = [
            HumanMessage(content="What is 2+2?"),
            AIMessage(content="It is 4."),
            HumanMessage(content="Thanks!"),
        ]
        result = await cm.maybe_summarise(msgs)
        llm.complete.assert_awaited_once()
        assert any("Summary" in (m.content or "") for m in result)

    async def test_always_preserves_system_message(self):
        llm = make_llm("Summary here.")
        cm = ContextManager(llm, threshold_tokens=1, preserve_last_n=1)
        sys_msg = SystemMessage(content="You are a helpful assistant.")
        msgs = [
            sys_msg,
            HumanMessage(content="msg1"),
            AIMessage(content="resp1"),
            HumanMessage(content="msg2"),
        ]
        result = await cm.maybe_summarise(msgs)
        assert result[0] is sys_msg

    async def test_always_preserves_last_n_messages(self):
        llm = make_llm("Summary.")
        preserve_n = 2
        cm = ContextManager(llm, threshold_tokens=1, preserve_last_n=preserve_n)
        msgs = [
            HumanMessage(content="old1"),
            AIMessage(content="old2"),
            HumanMessage(content="recent1"),
            AIMessage(content="recent2"),
        ]
        result = await cm.maybe_summarise(msgs)
        assert result[-2].content == "recent1"
        assert result[-1].content == "recent2"

    async def test_summary_replaces_middle_messages(self):
        llm = make_llm("Middle summary.")
        cm = ContextManager(llm, threshold_tokens=0, preserve_last_n=2)
        msgs = [
            SystemMessage(content="sys"),
            HumanMessage(content="A"),
            AIMessage(content="B"),
            HumanMessage(content="C"),
            AIMessage(content="D"),
        ]
        result = await cm.maybe_summarise(msgs)
        # sys + summary + last 2 = 4 total
        assert len(result) == 4
        assert isinstance(result[0], SystemMessage)
        assert "Summary" in result[1].content
        assert result[2].content == "C"
        assert result[3].content == "D"

    async def test_no_summarise_when_no_middle(self):
        llm = make_llm()
        cm = ContextManager(llm, threshold_tokens=1, preserve_last_n=10)
        msgs = [HumanMessage(content="A"), AIMessage(content="B")]
        result = await cm.maybe_summarise(msgs)
        assert result == msgs
        llm.complete.assert_not_awaited()
