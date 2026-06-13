from __future__ import annotations


def make_metrics(names: list[str], threshold: float, model: str) -> list:
    """Return DeepEval metric instances for the requested names."""
    from deepeval.metrics import GEval, FaithfulnessMetric, AnswerRelevancyMetric
    from deepeval.test_case import SingleTurnParams

    _valid = {"correctness", "faithfulness", "relevancy"}
    unknown = set(names) - _valid
    if unknown:
        raise ValueError(f"Unknown metric(s): {unknown}. Valid: {_valid}")

    result = []
    for name in names:
        if name == "correctness":
            result.append(
                GEval(
                    name="Correctness",
                    criteria="Does the actual output correctly answer the input question, consistent with the expected output?",
                    evaluation_params=[
                        SingleTurnParams.INPUT,
                        SingleTurnParams.ACTUAL_OUTPUT,
                        SingleTurnParams.EXPECTED_OUTPUT,
                    ],
                    model=model,
                    threshold=threshold,
                )
            )
        elif name == "faithfulness":
            result.append(
                FaithfulnessMetric(
                    threshold=threshold,
                    model=model,
                )
            )
        elif name == "relevancy":
            result.append(
                AnswerRelevancyMetric(
                    threshold=threshold,
                    model=model,
                )
            )
    return result
