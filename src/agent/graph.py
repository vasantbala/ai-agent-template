from __future__ import annotations

import functools
from typing import Any, Literal

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph

from agent.nodes.execute import execute
from agent.nodes.reason import reason
from agent.state import AgentState
from config.prompts import PromptManager
from config.settings import AgentConfig
from llm.client import LLMClient
from tools.registry import MCPRegistry


def _should_execute(state: AgentState) -> Literal["execute", "end"]:
    if state.error:
        return "end"
    pending = [t for t in state.tasks if t.status == "pending"]
    in_progress = [t for t in state.tasks if t.status == "in_progress"]
    if pending or (state.current_task_index < len(state.tasks) and in_progress):
        return "execute"
    # Check if there are tasks left by index
    if state.current_task_index < len(state.tasks):
        return "execute"
    return "end"


def build_graph(
    llm: LLMClient,
    registry: MCPRegistry,
    prompts: PromptManager,
    agent_config: AgentConfig,
) -> Any:
    async def _reason(state: AgentState) -> dict[str, Any]:
        tools = await registry.get_all_tools()
        return await reason(state, llm, tools, agent_config.max_iterations)

    async def _execute(state: AgentState) -> dict[str, Any]:
        return await execute(state, registry)

    builder = StateGraph(AgentState)
    builder.add_node("reason", _reason)
    builder.add_node("execute", _execute)

    builder.add_edge(START, "reason")
    builder.add_conditional_edges("reason", _should_execute, {"execute": "execute", "end": END})
    builder.add_edge("execute", "reason")

    return builder.compile()


async def run_agent(
    graph: Any,
    tenant_id: str,
    session_id: str,
    user_input: str,
    system_prompt: str,
    callbacks: list[Any] | None = None,
) -> AgentState:
    from langchain_core.messages import HumanMessage

    initial_state = AgentState(
        tenant_id=tenant_id,
        session_id=session_id,
        messages=[
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_input),
        ],
    )

    config: dict[str, Any] = {}
    if callbacks:
        config["callbacks"] = callbacks

    result = await graph.ainvoke(initial_state, config=config or None)
    return AgentState(**result)
