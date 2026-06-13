from __future__ import annotations

import os
import pytest

# DeepEval validates the judge model API key at metric construction time.
# Set a dummy key so unit tests don't require live credentials.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")

from evals.metrics import make_metrics


class TestMakeMetrics:
    def test_correctness_returns_geval(self):
        metrics = make_metrics(["correctness"], threshold=0.7, model="gpt-4o")
        assert len(metrics) == 1
        assert type(metrics[0]).__name__ == "GEval"

    def test_faithfulness_returns_faithfulness_metric(self):
        metrics = make_metrics(["faithfulness"], threshold=0.7, model="gpt-4o")
        assert len(metrics) == 1
        assert type(metrics[0]).__name__ == "FaithfulnessMetric"

    def test_relevancy_returns_answer_relevancy_metric(self):
        metrics = make_metrics(["relevancy"], threshold=0.7, model="gpt-4o")
        assert len(metrics) == 1
        assert type(metrics[0]).__name__ == "AnswerRelevancyMetric"

    def test_multiple_metrics_returned(self):
        metrics = make_metrics(["correctness", "faithfulness", "relevancy"], threshold=0.8, model="gpt-4o")
        assert len(metrics) == 3

    def test_threshold_applied_to_each_metric(self):
        metrics = make_metrics(["correctness", "faithfulness"], threshold=0.9, model="gpt-4o")
        for m in metrics:
            assert m.threshold == 0.9

    def test_unknown_metric_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown metric"):
            make_metrics(["hallucination"], threshold=0.7, model="gpt-4o")

    def test_mixed_valid_and_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown metric"):
            make_metrics(["correctness", "made_up"], threshold=0.7, model="gpt-4o")

    def test_empty_list_returns_empty(self):
        metrics = make_metrics([], threshold=0.7, model="gpt-4o")
        assert metrics == []
