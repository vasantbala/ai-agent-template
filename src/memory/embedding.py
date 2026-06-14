from __future__ import annotations

import litellm

from config.settings import EmbeddingSettings


class EmbeddingClient:
    def __init__(
        self,
        settings: EmbeddingSettings,
        llm_api_key: str,
        llm_base_url: str | None = None,
    ) -> None:
        self._model = settings.model
        self._api_key = settings.api_key or llm_api_key
        self._dimensions = settings.dimensions
        self._base_url = llm_base_url  # forwarded when embedding uses the same provider as LLM

    async def embed(self, text: str) -> list[float]:
        kwargs: dict = {
            "model": self._model,
            "input": [text],
            "api_key": self._api_key,
        }
        if self._base_url:
            kwargs["api_base"] = self._base_url
        response = await litellm.aembedding(**kwargs)
        return response.data[0]["embedding"]
