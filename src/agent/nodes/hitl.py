from __future__ import annotations

from langgraph.types import interrupt

from agent.state import AgentState


async def human_approval(state: AgentState) -> dict:
    pending = [t for t in state.tasks if t.status == "pending"]
    if not pending:
        return {}

    decision = interrupt({
        "question": "Approve the following tool calls?",
        "tasks": [{"tool": t.tool_name, "args": t.tool_args} for t in pending],
    })

    if decision != "approved":
        return {"error": f"Tool calls rejected by human: {decision}"}
    return {}
