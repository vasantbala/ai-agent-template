from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import litellm
from pydantic import BaseModel

from config.settings import LLMSettings

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
    ) -> dict[str, Any]:
        kwargs = self._base_kwargs()
        kwargs["messages"] = messages

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if response_format:
            kwargs["response_format"] = response_format

        response = await litellm.acompletion(**kwargs)
        return response  # type: ignore[return-value]
