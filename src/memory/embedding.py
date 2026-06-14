from __future__ import annotations

import litellm

from config.settings import EmbeddingSettings


class EmbeddingClient:
    def __init__(
        self,
        settings: EmbeddingSettings,
        llm_api_key: str,
        llm_provider: str | None = None,
        llm_base_url: str | None = None,
    ) -> None:
        # Only apply the LLM provider prefix when no dedicated embedding API key is
        # configured — a separate key means a different provider whose model names
        # must not be prefixed with the LLM provider.
        has_own_key = settings.api_key is not None
        self._model = self._resolve_model(settings.model, llm_provider if not has_own_key else None)
        self._api_key = settings.api_key or llm_api_key
        self._dimensions = settings.dimensions
        self._base_url = llm_base_url if not has_own_key else None

    @staticmethod
    def _resolve_model(model: str, provider: str | None) -> str:
        """Prefix the model name with the provider so LiteLLM can route it."""
        if provider == "openrouter" and not model.startswith("openrouter/"):
            return f"openrouter/{model}"
        if provider == "anthropic" and not model.startswith("anthropic/"):
            return f"anthropic/{model}"
        return model

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
