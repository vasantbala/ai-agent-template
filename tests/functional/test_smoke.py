"""
Functional smoke test — hits a real LLM and sends traces to Langfuse.

Requirements before running:
  1. Fill in your real API key in .env  (LLM__API_KEY=sk-or-...)
  2. Set Langfuse credentials in .env:
       LANGFUSE__PUBLIC_KEY=pk-lf-...
       LANGFUSE__SECRET_KEY=sk-lf-...
       LANGFUSE__HOST=https://cloud.langfuse.com   ← public cloud
  3. No Docker needed.

Run with:
  uv run pytest tests/functional/ -v -s

The -s flag lets you see the agent's actual response printed to stdout.
After the run, check https://cloud.langfuse.com to see the traces.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_ENV_FILE = str(Path(__file__).parent.parent.parent / ".env")


@pytest.fixture(scope="module")
def settings():
    from config.settings import Settings
    return Settings(_env_file=_ENV_FILE)  # type: ignore[call-arg]


@pytest.fixture(scope="module")
def tracer(settings):
    from observability.tracer import AgentTracer
    return AgentTracer(settings.langfuse, settings.tenant_id)


@pytest.fixture(scope="module")
def graph(settings):
    from llm.client import LLMClient
    from tools.registry import MCPRegistry
    from config.prompts import PromptManager
    from agent.graph import build_graph

    llm = LLMClient(settings.llm)
    registry = MCPRegistry(settings.mcp_servers)
    prompts = PromptManager(settings.agent.prompt_version)
    return build_graph(llm, registry, prompts, settings.agent)


async def _run(graph, tracer, settings, session_id: str, user_input: str):
    from agent.graph import run_agent
    from config.prompts import PromptManager
    from langchain_core.messages import AIMessage

    prompts = PromptManager(settings.agent.prompt_version)
    handler = tracer.callback_handler(session_id)

    state = await run_agent(
        graph=graph,
        tenant_id=settings.tenant_id,
        session_id=session_id,
        user_input=user_input,
        system_prompt=prompts.get_system_prompt(),
        callbacks=[handler],
    )
    tracer.flush()

    ai_messages = [m for m in state.messages if isinstance(m, AIMessage)]
    output = ai_messages[-1].content if ai_messages else ""
    return state, output


class TestAgentSmoke:
    async def test_simple_question_gets_a_response(self, graph, tracer, settings):
        """Agent answers a basic factual question — trace visible in Langfuse."""
        state, output = await _run(graph, tracer, settings, "smoke-1", "What is the capital of France? Answer in one sentence.")

        print(f"\n[Agent output]: {output}")

        assert output, "Agent produced no output"
        assert "paris" in output.lower(), f"Expected 'Paris' in response, got: {output}"

    async def test_multi_step_reasoning(self, graph, tracer, settings):
        """Agent handles a calculation with reasoning steps."""
        state, output = await _run(
            graph, tracer, settings, "smoke-2",
            "I have 3 apples. I give away 1 and then buy 4 more. How many apples do I have? Show your working."
        )

        print(f"\n[Agent output]: {output}")

        assert "6" in output, f"Expected answer '6' in response, got: {output}"

    async def test_tenant_id_preserved(self, graph, tracer, settings):
        """tenant_id survives through the full graph run."""
        from agent.graph import run_agent
        from config.prompts import PromptManager

        prompts = PromptManager(settings.agent.prompt_version)
        handler = tracer.callback_handler("smoke-3")
        state = await run_agent(
            graph=graph,
            tenant_id="acme-corp",
            session_id="smoke-3",
            user_input="Say hello.",
            system_prompt=prompts.get_system_prompt(),
            callbacks=[handler],
        )
        tracer.flush()
        assert state.tenant_id == "acme-corp"

    async def test_no_error_on_clean_run(self, graph, tracer, settings):
        """A clean run produces no error state."""
        state, output = await _run(graph, tracer, settings, "smoke-4", "What is 10 divided by 2?")

        print(f"\n[Agent output]: {output}")

        assert state.error is None, f"Unexpected error: {state.error}"
        assert output, "No output produced"
