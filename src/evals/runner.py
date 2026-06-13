from __future__ import annotations

import time
from typing import Awaitable, Callable

from pydantic import BaseModel

from config.settings import EvalConfig
from evals.golden import GoldenCase, GoldenDataset
from evals.metrics import make_metrics


class EvalResult(BaseModel):
    case_id: str
    input: str
    actual_output: str
    expected_output: str
    scores: dict[str, float]
    passed: dict[str, bool]
    latency_ms: float
    cost_usd: float | None = None


class EvalRunner:
    def __init__(self, config: EvalConfig) -> None:
        self._config = config

    async def run_case(
        self,
        case: GoldenCase,
        actual_output: str,
        latency_ms: float,
        cost_usd: float | None = None,
    ) -> EvalResult:
        from deepeval.test_case import LLMTestCase

        test_case = LLMTestCase(
            input=case.input,
            actual_output=actual_output,
            expected_output=case.expected_output,
            context=case.context or None,
        )

        metrics = make_metrics(
            names=self._config.metrics,
            threshold=self._config.threshold,
            model=self._config.model,
        )

        scores: dict[str, float] = {}
        passed: dict[str, bool] = {}
        for metric in metrics:
            await metric.a_measure(test_case, _show_indicator=False)
            name = metric.name.lower().replace(" ", "_")
            scores[name] = float(metric.score or 0.0)
            passed[name] = bool(metric.is_successful())

        return EvalResult(
            case_id=case.id,
            input=case.input,
            actual_output=actual_output,
            expected_output=case.expected_output,
            scores=scores,
            passed=passed,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )

    async def run_dataset(
        self,
        dataset: GoldenDataset,
        run_fn: Callable[[str], Awaitable[tuple[str, float, float | None]]],
    ) -> list[EvalResult]:
        results = []
        for case in dataset.load():
            actual_output, latency_ms, cost_usd = await run_fn(case.input)
            result = await self.run_case(case, actual_output, latency_ms, cost_usd)
            results.append(result)
        return results
