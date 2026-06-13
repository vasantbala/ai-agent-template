from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent.graph import build_graph
from api.routes.agent import router as agent_router
from api.routes.health import router as health_router
from config.prompts import PromptManager
from config.settings import get_settings
from guardrails.input import InputGuardrail
from guardrails.output import OutputGuardrail
from llm.client import LLMClient
from observability.tracer import AgentTracer
from tools.registry import MCPRegistry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    llm = LLMClient(settings.llm)
    registry = MCPRegistry(settings.mcp_servers, reliability=settings.reliability)
    prompts = PromptManager(settings.agent.prompt_version)
    tracer = AgentTracer(settings.langfuse, settings.tenant_id)

    await registry.connect_all()

    async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
        graph = build_graph(llm, registry, prompts, settings.agent, checkpointer=checkpointer)

        app.state.settings = settings
        app.state.llm = llm
        app.state.registry = registry
        app.state.prompts = prompts
        app.state.tracer = tracer
        app.state.graph = graph
        app.state.input_guardrail = InputGuardrail()
        app.state.output_guardrail = OutputGuardrail()

        yield

    await registry.disconnect_all()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Agent Template",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(agent_router)
    return app


app = create_app()
