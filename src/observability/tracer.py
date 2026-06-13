from __future__ import annotations

from typing import Any

from langfuse import Langfuse

from config.settings import LangfuseSettings


class AgentTracer:
    def __init__(self, settings: LangfuseSettings, tenant_id: str):
        self._lf = Langfuse(
            public_key=settings.public_key,
            secret_key=settings.secret_key,
            host=settings.host,
        )
        self._tenant_id = tenant_id

    def start_trace(self, session_id: str, user_input: str) -> Any:
        return self._lf.trace(
            name="agent-run",
            session_id=session_id,
            input=user_input,
            metadata={"tenant_id": self._tenant_id},
        )

    def span(self, trace: Any, name: str, input: dict[str, Any]) -> Any:
        return trace.span(name=name, input=input)

    def end_span(self, span: Any, output: dict[str, Any], error: str | None = None) -> None:
        span.end(output=output, level="ERROR" if error else "DEFAULT", status_message=error)

    def end_trace(self, trace: Any, output: str, usage: dict[str, int]) -> None:
        trace.update(output=output, usage=usage)
        self._lf.flush()
