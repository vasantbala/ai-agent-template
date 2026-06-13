from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage

from agent.state import AgentState, Task
from tools.registry import MCPRegistry


async def execute(state: AgentState, registry: MCPRegistry) -> dict[str, Any]:
    tasks = list(state.tasks)
    idx = state.current_task_index

    if idx >= len(tasks):
        return {}

    task = tasks[idx].model_copy()
    task.status = "in_progress"

    try:
        result = await registry.call_tool(task.tool_name or "", task.tool_args)
        task.status = "completed"
        task.result = result
    except Exception as exc:
        task.status = "failed"
        task.result = str(exc)
        result = str(exc)

    tasks[idx] = task

    tool_message = ToolMessage(
        content=result,
        tool_call_id=task.id,
        name=task.tool_name or "",
    )

    return {
        "tasks": tasks,
        "current_task_index": idx + 1,
        "messages": [tool_message],
    }
