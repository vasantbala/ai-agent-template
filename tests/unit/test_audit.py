from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from audit.logger import AuditLogger
from config.settings import AuditConfig


def make_logger(enabled: bool = True, tmp_path: Path | None = None) -> tuple[AuditLogger, Path | None]:
    if tmp_path is not None:
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(AuditConfig(enabled=enabled, log_path=str(log_file)))
        return logger, log_file
    logger = AuditLogger(AuditConfig(enabled=enabled, log_path=""))
    return logger, None


class TestAuditLogger:
    def test_disabled_writes_nothing(self, tmp_path):
        logger, log_file = make_logger(enabled=False, tmp_path=tmp_path)
        logger.tool_call("s1", "t1", "search", {}, "result", True)
        assert not log_file.exists()

    def test_tool_call_written_to_file(self, tmp_path):
        logger, log_file = make_logger(enabled=True, tmp_path=tmp_path)
        logger.tool_call("s1", "t1", "search", {"q": "hello"}, "some result", True)
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["event"] == "tool_call"
        assert event["session_id"] == "s1"
        assert event["tenant_id"] == "t1"
        assert event["tool_name"] == "search"
        assert event["success"] is True

    def test_llm_decision_written_to_file(self, tmp_path):
        logger, log_file = make_logger(enabled=True, tmp_path=tmp_path)
        logger.llm_decision("s2", "t2", iteration=3, tool_calls=["search", "read_file"])
        event = json.loads(log_file.read_text().strip())
        assert event["event"] == "llm_decision"
        assert event["iteration"] == 3
        assert event["tool_calls"] == ["search", "read_file"]

    def test_result_truncated_to_200_chars(self, tmp_path):
        logger, log_file = make_logger(enabled=True, tmp_path=tmp_path)
        long_result = "x" * 500
        logger.tool_call("s1", "t1", "tool", {}, long_result, True)
        event = json.loads(log_file.read_text().strip())
        assert len(event["result_preview"]) == 200

    def test_multiple_events_appended(self, tmp_path):
        logger, log_file = make_logger(enabled=True, tmp_path=tmp_path)
        logger.tool_call("s1", "t1", "tool_a", {}, "r1", True)
        logger.tool_call("s1", "t1", "tool_b", {}, "r2", False)
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2

    def test_event_has_timestamp(self, tmp_path):
        logger, log_file = make_logger(enabled=True, tmp_path=tmp_path)
        logger.llm_decision("s1", "t1", 1, [])
        event = json.loads(log_file.read_text().strip())
        assert "ts" in event
        assert "T" in event["ts"]  # ISO format contains 'T'

    def test_no_file_output_when_path_empty(self):
        logger, _ = make_logger(enabled=True, tmp_path=None)
        # Should not raise even without a file path
        logger.tool_call("s1", "t1", "tool", {}, "result", True)

    def test_failed_tool_call_recorded(self, tmp_path):
        logger, log_file = make_logger(enabled=True, tmp_path=tmp_path)
        logger.tool_call("s1", "t1", "tool", {}, "error message", False)
        event = json.loads(log_file.read_text().strip())
        assert event["success"] is False
