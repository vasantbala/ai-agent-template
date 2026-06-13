from __future__ import annotations

import litellm

from config.settings import EmbeddingSettings


class EmbeddingClient:
    def __init__(self, settings: EmbeddingSettings, llm_api_key: str) -> None:
        self._model = settings.model
        self._api_key = settings.api_key or llm_api_key
        self._dimensions = settings.dimensions

    async def embed(self, text: str) -> list[float]:
        response = await litellm.aembedding(
            model=self._model,
            input=[text],
            api_key=self._api_key,
        )
        return response.data[0]["embedding"]
