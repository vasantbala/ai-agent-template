import pytest
from unittest.mock import MagicMock, patch

from config.settings import LangfuseSettings
from observability.tracer import AgentTracer


def make_settings() -> LangfuseSettings:
    return LangfuseSettings(
        public_key="pk-test",
        secret_key="sk-test",
        host="http://localhost:3000",
    )


@pytest.fixture
def mock_langfuse():
    with patch("observability.tracer.Langfuse") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        yield instance


class TestAgentTracer:
    def test_initialises_langfuse_with_settings(self, mock_langfuse):
        with patch("observability.tracer.Langfuse") as mock_cls:
            mock_cls.return_value = MagicMock()
            settings = make_settings()
            AgentTracer(settings, "tenant-1")
            mock_cls.assert_called_once_with(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3000",
            )

    def test_start_trace_creates_trace_with_metadata(self, mock_langfuse):
        tracer = AgentTracer(make_settings(), "tenant-abc")
        tracer.start_trace("sess-1", "user input")
        mock_langfuse.trace.assert_called_once_with(
            name="agent-run",
            session_id="sess-1",
            input="user input",
            metadata={"tenant_id": "tenant-abc"},
        )

    def test_span_calls_trace_span(self, mock_langfuse):
        tracer = AgentTracer(make_settings(), "tenant-1")
        trace = MagicMock()
        tracer.span(trace, "reason", {"messages": []})
        trace.span.assert_called_once_with(name="reason", input={"messages": []})

    def test_end_span_calls_span_end_on_success(self, mock_langfuse):
        tracer = AgentTracer(make_settings(), "tenant-1")
        span = MagicMock()
        tracer.end_span(span, {"result": "ok"})
        span.end.assert_called_once_with(output={"result": "ok"}, level="DEFAULT", status_message=None)

    def test_end_span_marks_error_level_on_failure(self, mock_langfuse):
        tracer = AgentTracer(make_settings(), "tenant-1")
        span = MagicMock()
        tracer.end_span(span, {}, error="something failed")
        span.end.assert_called_once_with(output={}, level="ERROR", status_message="something failed")

    def test_end_trace_updates_and_flushes(self, mock_langfuse):
        tracer = AgentTracer(make_settings(), "tenant-1")
        trace = MagicMock()
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        tracer.end_trace(trace, "final output", usage)
        trace.update.assert_called_once_with(output="final output", usage=usage)
        mock_langfuse.flush.assert_called_once()
