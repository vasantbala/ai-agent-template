from __future__ import annotations

import os
from typing import Any

from langfuse import Langfuse, get_client
from langfuse.langchain import CallbackHandler
from langfuse.types import TraceContext

from config.settings import LangfuseSettings


class AgentTracer:
    def __init__(self, settings: LangfuseSettings, tenant_id: str):
        self._enabled = settings.enabled
        self._settings = settings
        self._tenant_id = tenant_id

        if settings.enabled:
            os.environ["LANGFUSE_PUBLIC_KEY"] = settings.public_key
            os.environ["LANGFUSE_SECRET_KEY"] = settings.secret_key
            os.environ["LANGFUSE_HOST"] = settings.host
        else:
            os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

    def callback_handler(self, session_id: str) -> CallbackHandler | None:
        """Returns a LangGraph callback handler, or None when Langfuse is disabled."""
        if not self._enabled:
            return None
        tc = TraceContext(
            session_id=session_id,
            user_id=self._tenant_id,
            trace_name="agent-run",
        )
        return CallbackHandler(trace_context=tc)

    def log_score(
        self,
        trace_id: str,
        name: str,
        value: float,
        comment: str | None = None,
    ) -> None:
        if not self._enabled:
            return
        get_client().create_score(
            trace_id=trace_id,
            name=name,
            value=value,
            comment=comment,
        )

    def flush(self) -> None:
        if not self._enabled:
            return
        get_client().flush()
