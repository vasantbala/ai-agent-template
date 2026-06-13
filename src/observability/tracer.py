from __future__ import annotations

import os
from typing import Any

from langfuse import Langfuse, get_client
from langfuse.langchain import CallbackHandler
from langfuse.types import TraceContext

from config.settings import LangfuseSettings


class AgentTracer:
    def __init__(self, settings: LangfuseSettings, tenant_id: str):
        # langfuse v4 CallbackHandler picks up credentials from env vars
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.public_key
        os.environ["LANGFUSE_SECRET_KEY"] = settings.secret_key
        os.environ["LANGFUSE_HOST"] = settings.host

        self._settings = settings
        self._tenant_id = tenant_id

    def callback_handler(self, session_id: str) -> CallbackHandler:
        """Returns a LangGraph callback handler that auto-traces every node and LLM call."""
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
        """Write an eval score back to Langfuse so it appears alongside the trace."""
        get_client().create_score(
            trace_id=trace_id,
            name=name,
            value=value,
            comment=comment,
        )

    def flush(self) -> None:
        get_client().flush()
