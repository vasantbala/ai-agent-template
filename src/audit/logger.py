from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from config.settings import AuditConfig

_log = logging.getLogger("audit")


class AuditLogger:
    def __init__(self, config: AuditConfig) -> None:
        self._enabled = config.enabled
        self._path = config.log_path or None  # empty string → no file output

    def _emit(self, event: dict[str, Any]) -> None:
        if not self._enabled:
            return
        line = json.dumps({"ts": datetime.now(UTC).isoformat(), **event})
        _log.info(line)
        if self._path:
            with open(self._path, "a") as f:
                f.write(line + "\n")

    def tool_call(
        self,
        session_id: str,
        tenant_id: str,
        tool_name: str,
        args: dict[str, Any],
        result: str,
        success: bool,
    ) -> None:
        self._emit({
            "event": "tool_call",
            "session_id": session_id,
            "tenant_id": tenant_id,
            "tool_name": tool_name,
            "args": args,
            "result_preview": result[:200],
            "success": success,
        })

    def llm_decision(
        self,
        session_id: str,
        tenant_id: str,
        iteration: int,
        tool_calls: list[str],
    ) -> None:
        self._emit({
            "event": "llm_decision",
            "session_id": session_id,
            "tenant_id": tenant_id,
            "iteration": iteration,
            "tool_calls": tool_calls,
        })
