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
    cost_enabled: bool = True,
) -> dict[str, Any]:
    if state.iteration >= max_iterations:
        return {"error": f"Max iterations ({max_iterations}) reached without completing all tasks"}

    # Summarise message history if over context threshold
    messages = state.messages
    if context_mgr is not None:
        messages = await context_mgr.maybe_summarise(messages)

    effective_tools = tools or None
    # On the first iteration, force the model to call a tool rather than answer
    # from training data. For agents that have a search tool, force that specific
    # tool so the model searches before fetching. For orchestrators (only call_*
    # tools), any tool is fine so use plain "required".
    tc: str | dict = "auto"
    if effective_tools and state.iteration == 0:
        search_tool = next(
            (t["function"]["name"] for t in effective_tools
             if "search" in t.get("function", {}).get("name", "").lower()),
            None,
        )
        if search_tool:
            tc = {"type": "function", "function": {"name": search_tool}}
        else:
            tc = "required"
    response = await llm.complete(
        messages=messages,
        tools=effective_tools,
        tool_choice=tc,
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

    # Accumulate cost
    new_cost = 0.0
    if cost_enabled:
        try:
            import litellm
            new_cost = litellm.completion_cost(completion_response=response) or 0.0
        except Exception:
            new_cost = 0.0

    choice = response.choices[0]
    tool_calls = choice.message.tool_calls or []
    new_tasks: list[Task] = []
    lc_tool_calls = []
    for tc in tool_calls:
        args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
        new_tasks.append(Task(
            description=f"Call {tc.function.name}",
            tool_call_id=tc.id,
            tool_name=tc.function.name,
            tool_args=args,
        ))
        lc_tool_calls.append({"id": tc.id, "name": tc.function.name, "args": args, "type": "tool_call"})

    ai_message = AIMessage(content=choice.message.content or "", tool_calls=lc_tool_calls)

    updates: dict[str, Any] = {
        "messages": [ai_message],
        "iteration": state.iteration + 1,
        "tokens_used": total_tokens,
        "cost_usd": state.cost_usd + new_cost,
    }
    if new_tasks:
        updates["tasks"] = new_tasks
        updates["current_task_index"] = 0

    return updates
