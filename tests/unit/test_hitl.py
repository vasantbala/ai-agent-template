from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from agent.state import AgentState, Task
from agent.nodes.hitl import human_approval


def make_state(**kwargs) -> AgentState:
    defaults = dict(tenant_id="t1", session_id="s1", tasks=[], messages=[])
    return AgentState(**{**defaults, **kwargs})


class TestHumanApproval:
    async def test_passes_through_when_no_pending_tasks(self):
        task = Task(description="done", status="completed", tool_name="calc", tool_args={})
        state = make_state(tasks=[task])
        result = await human_approval(state)
        assert result == {}

    async def test_passes_through_when_no_tasks(self):
        state = make_state(tasks=[])
        result = await human_approval(state)
        assert result == {}

    async def test_interrupts_with_pending_task_info(self):
        task = Task(description="run", status="pending", tool_name="bash", tool_args={"cmd": "ls"})
        state = make_state(tasks=[task])

        with patch("agent.nodes.hitl.interrupt") as mock_interrupt:
            mock_interrupt.return_value = "approved"
            result = await human_approval(state)

        mock_interrupt.assert_called_once()
        call_payload = mock_interrupt.call_args[0][0]
        assert call_payload["tasks"] == [{"tool": "bash", "args": {"cmd": "ls"}}]
        assert result == {}

    async def test_returns_error_on_rejection(self):
        task = Task(description="run", status="pending", tool_name="bash", tool_args={})
        state = make_state(tasks=[task])

        with patch("agent.nodes.hitl.interrupt") as mock_interrupt:
            mock_interrupt.return_value = "denied"
            result = await human_approval(state)

        assert "error" in result
        assert "rejected" in result["error"]
        assert "denied" in result["error"]

    async def test_passes_through_on_approved(self):
        task = Task(description="run", status="pending", tool_name="search", tool_args={"q": "ai"})
        state = make_state(tasks=[task])

        with patch("agent.nodes.hitl.interrupt") as mock_interrupt:
            mock_interrupt.return_value = "approved"
            result = await human_approval(state)

        assert result == {}

    async def test_only_pending_tasks_included_in_interrupt(self):
        done = Task(description="done", status="completed", tool_name="a", tool_args={})
        pending = Task(description="pending", status="pending", tool_name="b", tool_args={"x": 1})
        state = make_state(tasks=[done, pending])

        with patch("agent.nodes.hitl.interrupt") as mock_interrupt:
            mock_interrupt.return_value = "approved"
            await human_approval(state)

        payload = mock_interrupt.call_args[0][0]
        assert len(payload["tasks"]) == 1
        assert payload["tasks"][0]["tool"] == "b"
