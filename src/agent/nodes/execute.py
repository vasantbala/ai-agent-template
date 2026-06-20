from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import ToolMessage

from agent.state import AgentState, Task
from tools.registry import MCPRegistry

if TYPE_CHECKING:
    from agent.registry import AgentRegistry
    from security.permissions import ToolPermissionGuard


async def execute(
    state: AgentState,
    registry: MCPRegistry,
    agent_registry: AgentRegistry | None = None,
    permission_guard: ToolPermissionGuard | None = None,
) -> dict[str, Any]:
    tasks = list(state.tasks)
    idx = state.current_task_index

    if idx >= len(tasks):
        return {}

    task = tasks[idx].model_copy()
    task.status = "in_progress"

    try:
        tool_name = task.tool_name or ""
        if permission_guard:
            permission_guard.check(tool_name)
        if agent_registry and agent_registry.is_sub_agent_tool(tool_name):
            client = agent_registry.get(tool_name)
            result = await client.call(
                task=task.tool_args.get("task", ""),
                tenant_id=state.tenant_id,
                session_id=state.session_id,
                user_id=state.user_id,
            )
        else:
            result = await registry.call_tool(tool_name, task.tool_args)
        task.status = "completed"
        task.result = result
    except Exception as exc:
        task.status = "failed"
        task.result = str(exc)
        result = str(exc)

    tasks[idx] = task

    tool_message = ToolMessage(
        content=result,
        tool_call_id=task.tool_call_id or task.id,
        name=task.tool_name or "",
    )

    return {
        "tasks": tasks,
        "current_task_index": idx + 1,
        "messages": [tool_message],
    }
