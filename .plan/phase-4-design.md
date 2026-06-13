# Phase 4 Design — Evals & Quality

**Status:** DRAFT — awaiting user approval before any code is written  
**Goal:** Close the feedback loop. Measure output quality, track regressions, and make it easy to compare prompt versions or model choices objectively.

---

## What Phase 4 Delivers

- LLM-as-judge evaluation via DeepEval: correctness, faithfulness, answer relevancy
- Golden dataset: store expected input/output pairs, run evals against them on demand
- Cost and latency tracking per run — stored alongside quality scores
- Eval results written back to Langfuse for unified observability
- Prompt A/B: run the same golden dataset against two prompt versions and compare scores

---

## What We're NOT Building Yet

- Continuous eval in CI (that's Phase 6 with triggers)
- Per-user quality tracking or SLA dashboards
- Fine-tuning pipelines

---

## Directory Changes

```
src/
  evals/
    __init__.py
    config.py        # EvalConfig settings block
    runner.py        # EvalRunner — runs DeepEval metrics against a test case
    golden.py        # GoldenDataset — load/save golden cases from JSON files
    metrics.py       # metric factory: correctness, faithfulness, relevancy
evals/
  golden/
    default.json     # starter golden dataset (3-5 cases)
tests/
  unit/
    test_eval_runner.py
    test_golden_dataset.py
  evals/
    test_golden_suite.py   # runs the full golden dataset against the live agent
```

---

## Settings Changes

```python
class EvalConfig(BaseModel):
    enabled: bool = False
    metrics: list[Literal["correctness", "faithfulness", "relevancy"]] = ["correctness"]
    threshold: float = 0.7          # minimum passing score per metric
    model: str = "gpt-4o"           # judge model (can differ from agent model)
    golden_dataset_path: str = "evals/golden/default.json"

class Settings(BaseSettings):
    ...
    eval: EvalConfig = EvalConfig()
```

`.env.example` additions:
```
EVAL__ENABLED=false
EVAL__METRICS=["correctness"]
EVAL__THRESHOLD=0.7
EVAL__MODEL=gpt-4o
```

---

## Component Designs

### 1. GoldenDataset (`src/evals/golden.py`)

A golden case is an input + expected output + optional context. Cases are stored in a JSON file so non-engineers can add them without touching code.

```python
class GoldenCase(BaseModel):
    id: str
    input: str
    expected_output: str
    context: list[str] = []     # optional retrieval context for faithfulness
    tags: list[str] = []        # e.g. ["smoke", "regression", "prompt-v2"]

class GoldenDataset:
    def __init__(self, path: str): ...

    def load(self) -> list[GoldenCase]: ...
    def save(self, cases: list[GoldenCase]) -> None: ...
    def filter_by_tag(self, tag: str) -> list[GoldenCase]: ...
```

**Tests:** loads cases from JSON, saves and reloads preserves all fields, filter_by_tag returns matching subset only, empty file returns empty list.

---

### 2. Metrics (`src/evals/metrics.py`)

Thin factory over DeepEval metrics so callers never import DeepEval directly — easier to swap later.

```python
def make_metrics(names: list[str], threshold: float, model: str) -> list[BaseMetric]:
    # Returns the requested DeepEval metric instances.
    # correctness → GEval with "Does the actual output match the expected output?"
    # faithfulness → FaithfulnessMetric (requires context)
    # relevancy   → AnswerRelevancyMetric
```

**Tests:** returns correct metric types, threshold is applied to each metric, unknown metric name raises ValueError.

---

### 3. EvalRunner (`src/evals/runner.py`)

Runs a list of DeepEval metrics against a single test case and returns structured results.

```python
class EvalResult(BaseModel):
    case_id: str
    input: str
    actual_output: str
    expected_output: str
    scores: dict[str, float]     # metric_name → score
    passed: dict[str, bool]      # metric_name → passed threshold
    latency_ms: float
    cost_usd: float | None = None

class EvalRunner:
    def __init__(self, config: EvalConfig): ...

    async def run_case(
        self,
        case: GoldenCase,
        actual_output: str,
        latency_ms: float,
        cost_usd: float | None = None,
    ) -> EvalResult: ...

    async def run_dataset(
        self,
        dataset: GoldenDataset,
        run_fn: Callable[[str], Awaitable[tuple[str, float, float | None]]],
    ) -> list[EvalResult]: ...
    # run_fn takes input str, returns (output, latency_ms, cost_usd)
```

`run_dataset` is what the eval suite calls — it takes a callable that runs the agent and returns output + metrics, then evaluates each case.

**Tests:** passing score above threshold returns passed=True, score below threshold returns passed=False, run_case includes latency, all cases in dataset are evaluated.

---

### 4. Langfuse eval reporting

After each `run_dataset`, results are logged as Langfuse scores so they appear alongside traces.

```python
# In EvalRunner.run_dataset, after scoring:
tracer.log_score(
    trace_id=trace_id,
    name=metric_name,
    value=score,
    comment=f"golden_case:{case.id}",
)
```

This reuses the existing `AgentTracer` — no new observability infrastructure.

---

### 5. Golden eval test suite (`tests/evals/test_golden_suite.py`)

A pytest test that runs the full golden dataset against the live agent. Marked with `@pytest.mark.eval` so it's excluded from the normal unit/integration run and only runs explicitly:

```bash
uv run pytest tests/evals/ -m eval -v
```

Each golden case becomes one pytest test. A case is a pytest failure if any metric falls below threshold.

---

### 6. Prompt A/B comparison

No new code needed. Run the golden suite twice with different `AGENT__PROMPT_VERSION` values and compare the `EvalResult` JSONs. A helper script (`scripts/compare_evals.py`) prints a side-by-side diff of scores per case.

---

## Build Order

| # | Component | Files | Tests |
|---|---|---|---|
| 1 | EvalConfig in settings | `src/config/settings.py` | `test_config.py` (extend) |
| 2 | GoldenDataset + starter cases | `src/evals/golden.py`, `evals/golden/default.json` | `test_golden_dataset.py` |
| 3 | Metrics factory | `src/evals/metrics.py` | `test_eval_runner.py` (partial) |
| 4 | EvalRunner | `src/evals/runner.py` | `test_eval_runner.py` |
| 5 | Langfuse score reporting | `src/observability/tracer.py` (extend) | extend `test_tracer.py` |
| 6 | Golden eval test suite | `tests/evals/test_golden_suite.py` | run with `-m eval` |
| 7 | A/B comparison script | `scripts/compare_evals.py` | manual |

---

## Definition of Done for Phase 4

- [ ] All unit tests pass (`pytest tests/unit/`)
- [ ] Integration tests still pass (`pytest tests/integration/`)
- [ ] Golden suite passes with real LLM (`pytest tests/evals/ -m eval -v`)
- [ ] Eval scores visible in Langfuse UI alongside traces
- [ ] A/B comparison script produces readable diff between two prompt versions
