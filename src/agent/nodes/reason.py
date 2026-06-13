from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from agent.state import AgentState, Task
from config.settings import AgentConfig
from llm.client import LLMClient


async def reason(
    state: AgentState,
    llm: LLMClient,
    tools: list[dict[str, Any]],
    max_iterations: int,
) -> dict[str, Any]:
    if state.iteration >= max_iterations:
        return {"error": f"Max iterations ({max_iterations}) reached without completing all tasks"}

    response = await llm.complete(
        messages=[m.__class__(content=m.content) if hasattr(m, "content") else m
                  for m in state.messages],
        tools=tools or None,
    )

    choice = response.choices[0]
    ai_message = AIMessage(content=choice.message.content or "")

    # If the LLM called tools, convert them into Tasks
    tool_calls = choice.message.tool_calls or []
    new_tasks: list[Task] = []
    for tc in tool_calls:
        args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
        new_tasks.append(Task(
            description=f"Call {tc.function.name}",
            tool_name=tc.function.name,
            tool_args=args,
        ))

    updates: dict[str, Any] = {
        "messages": [ai_message],
        "iteration": state.iteration + 1,
    }
    if new_tasks:
        updates["tasks"] = new_tasks
        updates["current_task_index"] = 0

    return updates
