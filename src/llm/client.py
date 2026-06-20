from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import litellm
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel

from config.settings import LLMSettings


def _to_openai_dict(msg: Any) -> Any:
    if not isinstance(msg, BaseMessage):
        return msg
    if isinstance(msg, SystemMessage):
        return {"role": "system", "content": msg.content}
    if isinstance(msg, HumanMessage):
        return {"role": "user", "content": msg.content}
    if isinstance(msg, ToolMessage):
        return {"role": "tool", "content": str(msg.content), "tool_call_id": msg.tool_call_id}
    if isinstance(msg, AIMessage):
        d: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            d["tool_calls"] = [
                {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])}}
                for tc in msg.tool_calls
            ]
        return d
    return {"role": "user", "content": str(msg.content)}

litellm.drop_params = True  # ignore unsupported params per provider


class LLMClient:
    def __init__(self, settings: LLMSettings):
        self._settings = settings

    def _model_string(self) -> str:
        provider = self._settings.provider
        model = self._settings.model
        if provider == "openai":
            return model
        if provider == "anthropic":
            return f"anthropic/{model}"
        if provider == "openrouter":
            return f"openrouter/{model}"
        return model

    def _base_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model_string(),
            "api_key": self._settings.api_key,
            "max_tokens": self._settings.max_tokens,
            "temperature": self._settings.temperature,
        }
        if self._settings.base_url:
            kwargs["base_url"] = self._settings.base_url
        return kwargs

    async def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        response_format: type[BaseModel] | None = None,
        tool_choice: str | dict = "auto",
    ) -> dict[str, Any]:
        kwargs = self._base_kwargs()
        kwargs["messages"] = [_to_openai_dict(m) for m in messages]

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        if response_format:
            kwargs["response_format"] = response_format

        response = await litellm.acompletion(**kwargs)
        return response  # type: ignore[return-value]
