from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage

from agent.state import AgentState, Task
from llm.client import LLMClient

if TYPE_CHECKING:
    from reliability.context import ContextManager


async def reason(
    state: AgentState,
    llm: LLMClient,
    tools: list[dict[str, Any]],
    max_iterations: int,
    context_mgr: ContextManager | None = None,
    max_tokens: int = 0,
) -> dict[str, Any]:
    if state.iteration >= max_iterations:
        return {"error": f"Max iterations ({max_iterations}) reached without completing all tasks"}

    # Summarise message history if over context threshold
    messages = state.messages
    if context_mgr is not None:
        messages = await context_mgr.maybe_summarise(messages)

    response = await llm.complete(
        messages=[m.__class__(content=m.content) if hasattr(m, "content") else m
                  for m in messages],
        tools=tools or None,
    )

    # Accumulate token usage and enforce budget
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    new_tokens = prompt_tokens + completion_tokens
    total_tokens = state.tokens_used + new_tokens

    if max_tokens > 0 and total_tokens > max_tokens:
        return {
            "tokens_used": total_tokens,
            "error": f"Token budget exceeded: used {total_tokens}, limit {max_tokens}",
        }

    choice = response.choices[0]
    ai_message = AIMessage(content=choice.message.content or "")

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
        "tokens_used": total_tokens,
    }
    if new_tasks:
        updates["tasks"] = new_tasks
        updates["current_task_index"] = 0

    return updates
