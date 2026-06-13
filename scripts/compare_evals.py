#!/usr/bin/env python
"""Compare eval results from two prompt versions against the golden dataset.

Usage:
    # 1. Run evals for version A:
    AGENT__PROMPT_VERSION=v1 uv run pytest tests/evals/ -m eval -v \
        --json-report --json-report-file=evals/results/v1.json

    # Or run this script directly (it runs both versions back-to-back):
    uv run python scripts/compare_evals.py --versions v1 v2

The script loads settings from .env, runs the golden dataset twice (once per
prompt version), then prints a side-by-side score comparison per case.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def run_version(version: str, settings, cases) -> dict[str, dict[str, float]]:
    """Run each golden case through the agent at the given prompt version.

    Returns {case_id: {metric_name: score}}.
    """
    from langgraph.checkpoint.memory import InMemorySaver
    from llm.client import LLMClient
    from tools.registry import MCPRegistry
    from config.prompts import PromptManager
    from agent.graph import build_graph, run_agent
    from langchain_core.messages import AIMessage
    from evals.runner import EvalRunner
    from config.settings import EvalConfig

    # Override prompt version for this run
    agent_cfg = settings.agent.model_copy(update={"prompt_version": version})

    llm = LLMClient(settings.llm)
    registry = MCPRegistry(
        servers=settings.mcp_servers,
        retry_attempts=settings.reliability.mcp_retry_attempts,
        retry_base_delay=settings.reliability.mcp_retry_base_delay,
        circuit_breaker_failure_threshold=settings.reliability.circuit_breaker_failure_threshold,
        circuit_breaker_reset_timeout=settings.reliability.circuit_breaker_reset_timeout,
    )
    prompts = PromptManager(version)
    checkpointer = InMemorySaver()
    graph = build_graph(
        llm=llm,
        registry=registry,
        prompts=prompts,
        agent_config=agent_cfg,
        checkpointer=checkpointer,
        reliability=settings.reliability,
    )
    runner = EvalRunner(settings.eval)

    results: dict[str, dict[str, float]] = {}
    for case in cases:
        start = time.monotonic()
        final_state = await run_agent(
            graph=graph,
            tenant_id=settings.tenant_id,
            session_id=f"ab-{uuid.uuid4().hex[:8]}",
            user_input=case.input,
            system_prompt=prompts.get_system_prompt(),
        )
        latency_ms = (time.monotonic() - start) * 1000

        ai_messages = [m for m in final_state.messages if isinstance(m, AIMessage)]
        actual_output = ai_messages[-1].content if ai_messages else ""

        eval_result = await runner.run_case(case, actual_output, latency_ms)
        results[case.id] = eval_result.scores

    return results


def _print_comparison(cases, results_a: dict, results_b: dict, ver_a: str, ver_b: str) -> None:
    metrics = sorted({m for scores in results_a.values() for m in scores})
    col_w = 10

    header = f"{'case':<30}"
    for m in metrics:
        header += f"  {ver_a+'/'+m:>{col_w}}  {ver_b+'/'+m:>{col_w}}  {'delta':>{col_w}}"
    print(header)
    print("-" * len(header))

    wins_a = wins_b = ties = 0
    for case in cases:
        row = f"{case.id:<30}"
        for m in metrics:
            sa = results_a.get(case.id, {}).get(m, 0.0)
            sb = results_b.get(case.id, {}).get(m, 0.0)
            delta = sb - sa
            row += f"  {sa:>{col_w}.3f}  {sb:>{col_w}.3f}  {delta:>+{col_w}.3f}"
            if delta > 0.01:
                wins_b += 1
            elif delta < -0.01:
                wins_a += 1
            else:
                ties += 1
        print(row)

    print()
    print(f"Summary: {ver_a} wins={wins_a}  {ver_b} wins={wins_b}  ties={ties}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two prompt versions on the golden dataset")
    parser.add_argument("--versions", nargs=2, default=["v1", "v2"], metavar=("A", "B"),
                        help="Two prompt versions to compare (default: v1 v2)")
    args = parser.parse_args()
    ver_a, ver_b = args.versions

    from config.settings import _reset_settings, get_settings
    _reset_settings()
    try:
        settings = get_settings()
    except Exception as exc:
        print(f"ERROR: Could not load settings from .env — {exc}", file=sys.stderr)
        sys.exit(1)

    from evals.golden import GoldenDataset
    cases = GoldenDataset(settings.eval.golden_dataset_path).load()
    if not cases:
        print(f"No cases found at {settings.eval.golden_dataset_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Running {len(cases)} cases for version '{ver_a}'...")
    results_a = await run_version(ver_a, settings, cases)

    print(f"Running {len(cases)} cases for version '{ver_b}'...")
    results_b = await run_version(ver_b, settings, cases)

    print()
    _print_comparison(cases, results_a, results_b, ver_a, ver_b)


if __name__ == "__main__":
    asyncio.run(main())
