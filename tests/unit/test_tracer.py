import os
import pytest
from unittest.mock import MagicMock, patch

from config.settings import LangfuseSettings
from observability.tracer import AgentTracer


def make_settings() -> LangfuseSettings:
    return LangfuseSettings(
        enabled=True,
        public_key="pk-test",
        secret_key="sk-test",
        host="https://us.cloud.langfuse.com",
    )


class TestAgentTracer:
    def test_sets_langfuse_env_vars_on_init(self, monkeypatch):
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)

        AgentTracer(make_settings(), "tenant-1")

        assert os.environ["LANGFUSE_PUBLIC_KEY"] == "pk-test"
        assert os.environ["LANGFUSE_SECRET_KEY"] == "sk-test"
        assert os.environ["LANGFUSE_HOST"] == "https://us.cloud.langfuse.com"

    def test_callback_handler_uses_trace_context(self):
        with patch("observability.tracer.CallbackHandler") as mock_cls, \
             patch("observability.tracer.TraceContext") as mock_tc_cls:

            mock_tc_cls.return_value = {"session_id": "sess-1", "user_id": "tenant-abc", "trace_name": "agent-run"}
            mock_cls.return_value = MagicMock()

            tracer = AgentTracer(make_settings(), "tenant-abc")
            handler = tracer.callback_handler("sess-1")

            mock_tc_cls.assert_called_once_with(
                session_id="sess-1",
                user_id="tenant-abc",
                trace_name="agent-run",
            )
            mock_cls.assert_called_once_with(trace_context=mock_tc_cls.return_value)
            assert handler is mock_cls.return_value

    def test_callback_handler_uses_tenant_as_user_id(self):
        with patch("observability.tracer.CallbackHandler") as mock_cls, \
             patch("observability.tracer.TraceContext") as mock_tc_cls:

            mock_tc_cls.return_value = {}
            mock_cls.return_value = MagicMock()

            tracer = AgentTracer(make_settings(), "acme-corp")
            tracer.callback_handler("sess-x")

            assert mock_tc_cls.call_args.kwargs["user_id"] == "acme-corp"

    def test_different_sessions_produce_different_trace_contexts(self):
        with patch("observability.tracer.CallbackHandler") as mock_cls, \
             patch("observability.tracer.TraceContext") as mock_tc_cls:

            mock_tc_cls.side_effect = [{"session_id": "s1"}, {"session_id": "s2"}]
            mock_cls.side_effect = [MagicMock(), MagicMock()]

            tracer = AgentTracer(make_settings(), "tenant-1")
            tracer.callback_handler("sess-1")
            tracer.callback_handler("sess-2")

            calls = mock_tc_cls.call_args_list
            assert calls[0].kwargs["session_id"] == "sess-1"
            assert calls[1].kwargs["session_id"] == "sess-2"

    def test_flush_calls_global_langfuse_client(self):
        with patch("observability.tracer.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            tracer = AgentTracer(make_settings(), "tenant-1")
            tracer.flush()

            mock_get_client.assert_called_once()
            mock_client.flush.assert_called_once()

    def test_log_score_calls_create_score(self):
        with patch("observability.tracer.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            tracer = AgentTracer(make_settings(), "tenant-1")
            tracer.log_score(
                trace_id="trace-abc",
                name="correctness",
                value=0.92,
                comment="golden_case:capital-france",
            )

            mock_client.create_score.assert_called_once_with(
                trace_id="trace-abc",
                name="correctness",
                value=0.92,
                comment="golden_case:capital-france",
            )

    def test_log_score_without_comment(self):
        with patch("observability.tracer.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            tracer = AgentTracer(make_settings(), "tenant-1")
            tracer.log_score(trace_id="t1", name="relevancy", value=0.8)

            mock_client.create_score.assert_called_once_with(
                trace_id="t1",
                name="relevancy",
                value=0.8,
                comment=None,
            )
