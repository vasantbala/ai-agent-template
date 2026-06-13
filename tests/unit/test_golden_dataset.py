from __future__ import annotations

import json
import pytest

from evals.golden import GoldenCase, GoldenDataset


@pytest.fixture
def dataset_path(tmp_path):
    return str(tmp_path / "cases.json")


def write_cases(path: str, cases: list[dict]) -> None:
    import pathlib
    pathlib.Path(path).write_text(json.dumps(cases))


class TestGoldenCase:
    def test_minimal_case(self):
        c = GoldenCase(id="c1", input="hello", expected_output="world")
        assert c.context == []
        assert c.tags == []

    def test_full_case(self):
        c = GoldenCase(
            id="c2",
            input="q",
            expected_output="a",
            context=["ctx"],
            tags=["smoke"],
        )
        assert c.context == ["ctx"]
        assert c.tags == ["smoke"]


class TestGoldenDataset:
    def test_load_returns_empty_when_file_missing(self, dataset_path):
        ds = GoldenDataset(dataset_path)
        assert ds.load() == []

    def test_load_parses_cases(self, dataset_path):
        write_cases(dataset_path, [
            {"id": "c1", "input": "q1", "expected_output": "a1"},
            {"id": "c2", "input": "q2", "expected_output": "a2", "tags": ["smoke"]},
        ])
        ds = GoldenDataset(dataset_path)
        cases = ds.load()
        assert len(cases) == 2
        assert cases[0].id == "c1"
        assert cases[1].tags == ["smoke"]

    def test_save_and_reload_preserves_all_fields(self, dataset_path):
        original = [
            GoldenCase(
                id="c1",
                input="What is AI?",
                expected_output="AI is artificial intelligence.",
                context=["AI stands for artificial intelligence."],
                tags=["smoke", "regression"],
            )
        ]
        ds = GoldenDataset(dataset_path)
        ds.save(original)
        reloaded = ds.load()

        assert len(reloaded) == 1
        assert reloaded[0].id == "c1"
        assert reloaded[0].input == "What is AI?"
        assert reloaded[0].expected_output == "AI is artificial intelligence."
        assert reloaded[0].context == ["AI stands for artificial intelligence."]
        assert reloaded[0].tags == ["smoke", "regression"]

    def test_filter_by_tag_returns_matching_subset(self, dataset_path):
        write_cases(dataset_path, [
            {"id": "c1", "input": "q", "expected_output": "a", "tags": ["smoke"]},
            {"id": "c2", "input": "q", "expected_output": "a", "tags": ["regression"]},
            {"id": "c3", "input": "q", "expected_output": "a", "tags": ["smoke", "regression"]},
        ])
        ds = GoldenDataset(dataset_path)
        smoke = ds.filter_by_tag("smoke")
        assert len(smoke) == 2
        assert all("smoke" in c.tags for c in smoke)

    def test_filter_by_tag_returns_empty_when_no_match(self, dataset_path):
        write_cases(dataset_path, [
            {"id": "c1", "input": "q", "expected_output": "a", "tags": ["smoke"]},
        ])
        ds = GoldenDataset(dataset_path)
        assert ds.filter_by_tag("faithfulness") == []

    def test_save_creates_parent_dirs(self, tmp_path):
        path = str(tmp_path / "nested" / "dir" / "cases.json")
        ds = GoldenDataset(path)
        ds.save([GoldenCase(id="c1", input="q", expected_output="a")])
        assert ds.load()[0].id == "c1"

    def test_default_golden_dataset_loads(self):
        ds = GoldenDataset("evals/golden/default.json")
        cases = ds.load()
        assert len(cases) >= 3
        assert all(c.id for c in cases)
        assert all(c.input for c in cases)
        assert all(c.expected_output for c in cases)
