from __future__ import annotations

import uuid

import httpx

from config.settings import SubAgentConfig


class SubAgentError(Exception):
    pass


class SubAgentClient:
    def __init__(self, config: SubAgentConfig) -> None:
        self._config = config

    async def call(
        self,
        task: str,
        tenant_id: str,
        session_id: str,
        user_id: str | None = None,
    ) -> str:
        sub_session_id = f"{session_id}-{self._config.name}-{uuid.uuid4().hex[:8]}"
        body = {
            "input": task,
            "tenant_id": tenant_id,
            "session_id": sub_session_id,
            "user_id": user_id,
        }
        url = f"{self._config.url.rstrip('/')}/v1/agent/run"
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout) as client:
                response = await client.post(url, json=body)
                response.raise_for_status()
                return response.json().get("output", "")
        except httpx.TimeoutException as exc:
            raise SubAgentError(
                f"Sub-agent '{self._config.name}' timed out after {self._config.timeout}s"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise SubAgentError(
                f"Sub-agent '{self._config.name}' returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise SubAgentError(
                f"Sub-agent '{self._config.name}' request failed: {exc}"
            ) from exc
