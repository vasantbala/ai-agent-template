from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from agent.state import AgentState
from config.settings import MemoryConfig
from memory.store import MemoryStore


async def retrieve_memories(
    state: AgentState,
    store: MemoryStore,
    config: MemoryConfig,
) -> dict:
    if not config.enabled:
        return {}

    # Use the last human message as the retrieval query
    human_msgs = [m for m in state.messages if isinstance(m, HumanMessage)]
    if not human_msgs:
        return {}

    query = human_msgs[-1].content
    if not isinstance(query, str) or not query.strip():
        return {}

    memories = await store.retrieve(
        query=query,
        tenant_id=state.tenant_id,
        scope=config.scope,
        session_id=state.session_id,
        top_k=config.top_k,
    )

    if not memories:
        return {}

    memory_text = "\n".join(f"- {m}" for m in memories)
    context_msg = SystemMessage(
        content=f"Relevant context from past sessions:\n{memory_text}"
    )
    return {"messages": [context_msg]}
