from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class GoldenCase(BaseModel):
    id: str
    input: str
    expected_output: str
    context: list[str] = []
    tags: list[str] = []


class GoldenDataset:
    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def load(self) -> list[GoldenCase]:
        if not self._path.exists():
            return []
        data = json.loads(self._path.read_text())
        return [GoldenCase(**c) for c in data]

    def save(self, cases: list[GoldenCase]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps([c.model_dump() for c in cases], indent=2)
        )

    def filter_by_tag(self, tag: str) -> list[GoldenCase]:
        return [c for c in self.load() if tag in c.tags]
