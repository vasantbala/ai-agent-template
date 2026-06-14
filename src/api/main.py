from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent.graph import build_graph
from agent.registry import AgentRegistry
from api.routes.agent import router as agent_router
from api.routes.health import router as health_router
from api.routes.stream import router as stream_router
from api.routes.webhook import router as webhook_router
from auth.middleware import require_auth
from triggers.scheduler import start_scheduler
from config.prompts import PromptManager
from config.settings import get_settings
from guardrails.input import InputGuardrail
from guardrails.output import OutputGuardrail
from llm.client import LLMClient
from memory.embedding import EmbeddingClient
from memory.store import MemoryStore
from observability.tracer import AgentTracer
from tools.registry import MCPRegistry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    llm = LLMClient(settings.llm)
    registry = MCPRegistry(settings.mcp_servers, reliability=settings.reliability)
    prompts = PromptManager(settings.agent.prompt_version)
    tracer = AgentTracer(settings.langfuse, settings.tenant_id)

    embedder = EmbeddingClient(settings.embedding, llm_api_key=settings.llm.api_key)
    memory_store = MemoryStore(settings.memory, embedder)

    if settings.memory.enabled:
        await memory_store.ensure_collection(dimensions=settings.embedding.dimensions)

    agent_registry = AgentRegistry(settings.agent.sub_agents)

    await registry.connect_all()

    async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
        graph = build_graph(
            llm, registry, prompts, settings.agent,
            checkpointer=checkpointer,
            reliability=settings.reliability,
            memory_store=memory_store if settings.memory.enabled else None,
            memory_config=settings.memory,
            agent_registry=agent_registry,
            cost_config=settings.cost,
        )

        app.state.settings = settings
        app.state.llm = llm
        app.state.registry = registry
        app.state.prompts = prompts
        app.state.tracer = tracer
        app.state.graph = graph
        app.state.memory_store = memory_store if settings.memory.enabled else None
        app.state.input_guardrail = InputGuardrail()
        app.state.output_guardrail = OutputGuardrail()

        scheduler = start_scheduler(app, settings.schedule)

        yield

        if scheduler is not None:
            scheduler.shutdown(wait=False)

    await registry.disconnect_all()


def create_app() -> FastAPI:
    from fastapi import Depends

    app = FastAPI(
        title="AI Agent Template",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)  # no auth — uptime checks must pass without a key
    app.include_router(agent_router, dependencies=[Depends(require_auth)])
    app.include_router(stream_router, dependencies=[Depends(require_auth)])
    app.include_router(webhook_router, dependencies=[Depends(require_auth)])
    return app


app = create_app()
