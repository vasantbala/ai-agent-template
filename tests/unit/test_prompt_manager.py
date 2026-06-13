import pytest
from pathlib import Path

from config.prompts import PromptManager


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    v1 = tmp_path / "v1"
    v1.mkdir()
    (v1 / "system.md").write_text("You are a test agent.\n", encoding="utf-8")
    return tmp_path


class TestPromptManager:
    def test_loads_system_prompt(self, prompts_dir: Path):
        pm = PromptManager(version="v1", prompts_dir=prompts_dir)
        assert pm.get_system_prompt() == "You are a test agent."

    def test_strips_whitespace(self, prompts_dir: Path):
        (prompts_dir / "v1" / "system.md").write_text("  Hello agent.  \n\n", encoding="utf-8")
        pm = PromptManager(version="v1", prompts_dir=prompts_dir)
        assert pm.get_system_prompt() == "Hello agent."

    def test_missing_version_raises_file_not_found(self, prompts_dir: Path):
        pm = PromptManager(version="v99", prompts_dir=prompts_dir)
        with pytest.raises(FileNotFoundError, match="v99"):
            pm.get_system_prompt()

    def test_error_message_includes_path_hint(self, prompts_dir: Path):
        pm = PromptManager(version="v99", prompts_dir=prompts_dir)
        with pytest.raises(FileNotFoundError, match="prompts/v99/system.md"):
            pm.get_system_prompt()

    def test_default_v1_prompt_exists(self):
        pm = PromptManager(version="v1")
        prompt = pm.get_system_prompt()
        assert len(prompt) > 0

    def test_multiple_versions_isolated(self, tmp_path: Path):
        (tmp_path / "v1").mkdir()
        (tmp_path / "v2").mkdir()
        (tmp_path / "v1" / "system.md").write_text("Version one.", encoding="utf-8")
        (tmp_path / "v2" / "system.md").write_text("Version two.", encoding="utf-8")

        assert PromptManager("v1", tmp_path).get_system_prompt() == "Version one."
        assert PromptManager("v2", tmp_path).get_system_prompt() == "Version two."
