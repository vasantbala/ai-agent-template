from __future__ import annotations

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from config.settings import SubAgentConfig
from agent.subagent import SubAgentClient, SubAgentError


def make_config(**kwargs) -> SubAgentConfig:
    return SubAgentConfig(**{
        "name": "worker",
        "url": "http://localhost:8002",
        "description": "A worker agent",
        **kwargs,
    })


def make_response(output: str = "done", status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"output": output}
    resp.raise_for_status = MagicMock()
    return resp


class TestSubAgentClient:
    async def test_successful_call_returns_output(self):
        client = SubAgentClient(make_config())
        resp = make_response("the answer")

        with patch("agent.subagent.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=resp)
            mock_cls.return_value = mock_http

            result = await client.call("do something", "t1", "sess-1")

        assert result == "the answer"

    async def test_posts_to_correct_url(self):
        client = SubAgentClient(make_config(url="http://myagent:9000"))
        resp = make_response()

        with patch("agent.subagent.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=resp)
            mock_cls.return_value = mock_http

            await client.call("task", "t1", "sess-1")

        call_url = mock_http.post.call_args.args[0]
        assert call_url == "http://myagent:9000/v1/agent/run"

    async def test_session_id_scoped_to_parent_and_name(self):
        client = SubAgentClient(make_config(name="researcher"))
        resp = make_response()

        with patch("agent.subagent.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=resp)
            mock_cls.return_value = mock_http

            await client.call("task", "t1", "parent-sess")

        body = mock_http.post.call_args.kwargs["json"]
        assert body["session_id"].startswith("parent-sess-researcher-")

    async def test_passes_tenant_and_user_id(self):
        client = SubAgentClient(make_config())
        resp = make_response()

        with patch("agent.subagent.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=resp)
            mock_cls.return_value = mock_http

            await client.call("task", "acme", "sess-1", user_id="alice")

        body = mock_http.post.call_args.kwargs["json"]
        assert body["tenant_id"] == "acme"
        assert body["user_id"] == "alice"

    async def test_http_error_raises_subagent_error(self):
        client = SubAgentClient(make_config())

        with patch("agent.subagent.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            resp = MagicMock()
            resp.status_code = 500
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "error", request=MagicMock(), response=resp
            )
            mock_http.post = AsyncMock(return_value=resp)
            mock_cls.return_value = mock_http

            with pytest.raises(SubAgentError, match="HTTP 500"):
                await client.call("task", "t1", "sess-1")

    async def test_timeout_raises_subagent_error(self):
        client = SubAgentClient(make_config(timeout=5.0))

        with patch("agent.subagent.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            mock_cls.return_value = mock_http

            with pytest.raises(SubAgentError, match="timed out after 5.0s"):
                await client.call("task", "t1", "sess-1")

    async def test_connection_error_raises_subagent_error(self):
        client = SubAgentClient(make_config())

        with patch("agent.subagent.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(
                side_effect=httpx.ConnectError("connection refused")
            )
            mock_cls.return_value = mock_http

            with pytest.raises(SubAgentError, match="request failed"):
                await client.call("task", "t1", "sess-1")

    async def test_trailing_slash_in_url_handled(self):
        client = SubAgentClient(make_config(url="http://localhost:8002/"))
        resp = make_response()

        with patch("agent.subagent.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=resp)
            mock_cls.return_value = mock_http

            await client.call("task", "t1", "sess-1")

        call_url = mock_http.post.call_args.args[0]
        assert call_url == "http://localhost:8002/v1/agent/run"
