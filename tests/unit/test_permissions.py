from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from agent.nodes.execute import execute
from agent.state import AgentState, Task
from security.permissions import ToolPermissionGuard, ToolPermissionError
from tools.registry import MCPRegistry


def make_state(**overrides) -> AgentState:
    defaults = {
        "tenant_id": "test",
        "session_id": "sess-1",
        "messages": [],
    }
    return AgentState(**(defaults | overrides))


class TestToolPermissionGuard:
    def test_empty_allowlist_permits_all(self):
        guard = ToolPermissionGuard([])
        guard.check("any_tool")  # must not raise

    def test_tool_in_allowlist_permitted(self):
        guard = ToolPermissionGuard(["read_file", "search"])
        guard.check("read_file")  # must not raise

    def test_tool_not_in_allowlist_raises(self):
        guard = ToolPermissionGuard(["read_file"])
        with pytest.raises(ToolPermissionError, match="search"):
            guard.check("search")

    def test_error_message_includes_allowed_list(self):
        guard = ToolPermissionGuard(["read_file"])
        with pytest.raises(ToolPermissionError, match="read_file"):
            guard.check("forbidden_tool")

    def test_single_tool_allowlist(self):
        guard = ToolPermissionGuard(["only_this"])
        guard.check("only_this")
        with pytest.raises(ToolPermissionError):
            guard.check("anything_else")


class TestExecuteNodePermissions:
    async def test_blocked_tool_marks_task_failed(self):
        registry = AsyncMock(spec=MCPRegistry)
        guard = ToolPermissionGuard(["allowed_tool"])

        task = Task(description="blocked", tool_name="forbidden", tool_args={})
        state = make_state(tasks=[task], current_task_index=0)

        result = await execute(state, registry, permission_guard=guard)

        assert result["tasks"][0].status == "failed"
        assert "forbidden" in result["tasks"][0].result
        registry.call_tool.assert_not_awaited()

    async def test_allowed_tool_executes_normally(self):
        registry = AsyncMock(spec=MCPRegistry)
        registry.call_tool.return_value = "ok"
        guard = ToolPermissionGuard(["search"])

        task = Task(description="search", tool_name="search", tool_args={})
        state = make_state(tasks=[task], current_task_index=0)

        result = await execute(state, registry, permission_guard=guard)

        assert result["tasks"][0].status == "completed"
        registry.call_tool.assert_awaited_once()

    async def test_no_guard_allows_all_tools(self):
        registry = AsyncMock(spec=MCPRegistry)
        registry.call_tool.return_value = "result"

        task = Task(description="any", tool_name="any_tool", tool_args={})
        state = make_state(tasks=[task], current_task_index=0)

        result = await execute(state, registry, permission_guard=None)

        assert result["tasks"][0].status == "completed"
