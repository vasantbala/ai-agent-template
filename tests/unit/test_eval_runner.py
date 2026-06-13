from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")

from config.settings import EvalConfig
from evals.golden import GoldenCase, GoldenDataset
from evals.runner import EvalResult, EvalRunner


def make_config(**kwargs) -> EvalConfig:
    return EvalConfig(**{"metrics": ["correctness"], "threshold": 0.7, "model": "gpt-4o", **kwargs})


def make_case(**kwargs) -> GoldenCase:
    return GoldenCase(**{"id": "c1", "input": "q", "expected_output": "a", **kwargs})


def make_mock_metric(name: str = "Correctness", score: float = 0.9, success: bool = True) -> MagicMock:
    m = MagicMock()
    m.name = name
    m.score = score
    m.is_successful = MagicMock(return_value=success)
    m.a_measure = AsyncMock()
    return m


class TestEvalResult:
    def test_model_fields(self):
        r = EvalResult(
            case_id="c1",
            input="q",
            actual_output="a",
            expected_output="a",
            scores={"correctness": 0.9},
            passed={"correctness": True},
            latency_ms=100.0,
        )
        assert r.cost_usd is None
        assert r.latency_ms == 100.0


class TestEvalRunner:
    @pytest.fixture
    def runner(self):
        return EvalRunner(make_config())

    async def test_run_case_returns_eval_result(self, runner):
        case = make_case()
        mock_metric = make_mock_metric(score=0.9, success=True)

        with patch("evals.runner.make_metrics", return_value=[mock_metric]):
            result = await runner.run_case(case, actual_output="answer", latency_ms=123.0)

        assert isinstance(result, EvalResult)
        assert result.case_id == "c1"
        assert result.input == "q"
        assert result.actual_output == "answer"
        assert result.latency_ms == 123.0

    async def test_score_above_threshold_passes(self, runner):
        case = make_case()
        mock_metric = make_mock_metric(name="Correctness", score=0.95, success=True)

        with patch("evals.runner.make_metrics", return_value=[mock_metric]):
            result = await runner.run_case(case, actual_output="great answer", latency_ms=50.0)

        assert result.scores["correctness"] == 0.95
        assert result.passed["correctness"] is True

    async def test_score_below_threshold_fails(self, runner):
        case = make_case()
        mock_metric = make_mock_metric(name="Correctness", score=0.3, success=False)

        with patch("evals.runner.make_metrics", return_value=[mock_metric]):
            result = await runner.run_case(case, actual_output="bad answer", latency_ms=50.0)

        assert result.scores["correctness"] == 0.3
        assert result.passed["correctness"] is False

    async def test_run_case_includes_cost(self, runner):
        case = make_case()
        mock_metric = make_mock_metric()

        with patch("evals.runner.make_metrics", return_value=[mock_metric]):
            result = await runner.run_case(case, actual_output="a", latency_ms=10.0, cost_usd=0.002)

        assert result.cost_usd == 0.002

    async def test_run_dataset_evaluates_all_cases(self, runner):
        cases = [
            GoldenCase(id="c1", input="q1", expected_output="a1"),
            GoldenCase(id="c2", input="q2", expected_output="a2"),
            GoldenCase(id="c3", input="q3", expected_output="a3"),
        ]

        mock_dataset = MagicMock(spec=GoldenDataset)
        mock_dataset.load.return_value = cases

        call_count = 0

        async def run_fn(inp: str):
            nonlocal call_count
            call_count += 1
            return f"output for {inp}", 100.0, None

        mock_metric = make_mock_metric()
        with patch("evals.runner.make_metrics", return_value=[mock_metric]):
            results = await runner.run_dataset(mock_dataset, run_fn)

        assert len(results) == 3
        assert call_count == 3
        assert {r.case_id for r in results} == {"c1", "c2", "c3"}

    async def test_run_dataset_passes_input_to_run_fn(self, runner):
        cases = [GoldenCase(id="c1", input="specific input", expected_output="expected")]
        mock_dataset = MagicMock(spec=GoldenDataset)
        mock_dataset.load.return_value = cases

        received_inputs = []

        async def run_fn(inp: str):
            received_inputs.append(inp)
            return "output", 50.0, None

        mock_metric = make_mock_metric()
        with patch("evals.runner.make_metrics", return_value=[mock_metric]):
            await runner.run_dataset(mock_dataset, run_fn)

        assert received_inputs == ["specific input"]
