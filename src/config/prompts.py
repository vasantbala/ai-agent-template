from __future__ import annotations

from datetime import date
from pathlib import Path


_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


class PromptManager:
    def __init__(self, version: str, prompts_dir: Path = _PROMPTS_DIR):
        self._version = version
        self._system_path = prompts_dir / version / "system.md"

    def get_system_prompt(self) -> str:
        if not self._system_path.exists():
            raise FileNotFoundError(
                f"System prompt not found for version '{self._version}' "
                f"at {self._system_path}. "
                f"Create prompts/{self._version}/system.md to fix this."
            )
        text = self._system_path.read_text(encoding="utf-8").strip()
        today = date.today().isoformat()
        return f"Today's date is {today}.\n\n{text}"
