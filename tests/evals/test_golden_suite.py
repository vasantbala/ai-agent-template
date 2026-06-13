"""Golden eval suite — runs the full golden dataset against the live agent.

Run with:
    uv run pytest tests/evals/ -m eval -v

Requires valid .env with LLM credentials and (optionally) OPENAI_API_KEY
for the DeepEval judge model. Skipped automatically if credentials are missing.
"""
from __future__ import annotations

import os
import time
import pytest

pytestmark = pytest.mark.eval


def _load_settings():
    """Load settings from .env. Returns None if required env vars are absent."""
    try:
        from config.settings import _reset_settings, get_settings
        _reset_settings()
        return get_settings()
    except Exception:
        return None


@pytest.fixture(scope="module")
def settings():
    s = _load_settings()
    if s is None:
        pytest.skip("Missing .env credentials — skipping eval suite")
    return s


@pytest.fixture(scope="module")
async def agent_graph(settings):
    from langgraph.checkpoint.memory import InMemorySaver
    from llm.client import LLMClient
    from tools.registry import MCPRegistry
    from config.prompts import PromptManager
    from agent.graph import build_graph

    llm = LLMClient(settings.llm)
    registry = MCPRegistry(settings.mcp_servers, reliability=settings.reliability)
    prompts = PromptManager(settings.agent.prompt_version)
    checkpointer = InMemorySaver()
    graph = build_graph(
        llm=llm,
        registry=registry,
        prompts=prompts,
        agent_config=settings.agent,
        checkpointer=checkpointer,
        reliability=settings.reliability,
    )
    return graph, llm, prompts


@pytest.fixture(scope="module")
def eval_runner(settings):
    from evals.runner import EvalRunner
    return EvalRunner(settings.eval, llm_settings=settings.llm)


@pytest.fixture(scope="module")
def golden_cases(settings):
    from evals.golden import GoldenDataset
    ds = GoldenDataset(settings.eval.golden_dataset_path)
    cases = ds.load()
    if not cases:
        pytest.skip(f"No golden cases found at {settings.eval.golden_dataset_path}")
    return cases


def pytest_generate_tests(metafunc):
    """Parametrize test_golden_case with one ID per golden case (read at collection time)."""
    if "golden_case" in metafunc.fixturenames:
        s = _load_settings()
        if s is None:
            metafunc.parametrize("golden_case", [], indirect=False)
            return
        from evals.golden import GoldenDataset
        cases = GoldenDataset(s.eval.golden_dataset_path).load()
        metafunc.parametrize("golden_case", cases, ids=[c.id for c in cases])


@pytest.mark.eval
async def test_golden_case(golden_case, agent_graph, eval_runner, settings):
    """Each golden case becomes a separate pytest test. Fails if any metric is below threshold."""
    from agent.graph import run_agent
    import uuid

    graph, llm, prompts = agent_graph

    start = time.monotonic()
    final_state = await run_agent(
        graph=graph,
        tenant_id=settings.tenant_id,
        session_id=f"eval-{uuid.uuid4().hex[:8]}",
        user_input=golden_case.input,
        system_prompt=prompts.get_system_prompt(),
    )
    latency_ms = (time.monotonic() - start) * 1000

    from langchain_core.messages import AIMessage
    ai_messages = [m for m in final_state.messages if isinstance(m, AIMessage)]
    actual_output = ai_messages[-1].content if ai_messages else ""

    result = await eval_runner.run_case(
        case=golden_case,
        actual_output=actual_output,
        latency_ms=latency_ms,
    )

    failed_metrics = [name for name, ok in result.passed.items() if not ok]
    assert not failed_metrics, (
        f"Case '{golden_case.id}' failed metrics {failed_metrics}.\n"
        f"Input: {golden_case.input}\n"
        f"Expected: {golden_case.expected_output}\n"
        f"Actual: {actual_output}\n"
        f"Scores: {result.scores}"
    )
