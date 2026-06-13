from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from config.settings import EmbeddingSettings
from memory.embedding import EmbeddingClient


def make_settings(**kwargs) -> EmbeddingSettings:
    return EmbeddingSettings(**{"model": "text-embedding-3-small", "dimensions": 1536, **kwargs})


def make_embedding_response(vector: list[float]) -> MagicMock:
    resp = MagicMock()
    resp.data = [{"embedding": vector}]
    return resp


class TestEmbeddingClient:
    async def test_returns_embedding_vector(self):
        vector = [0.1, 0.2, 0.3]
        with patch("memory.embedding.litellm.aembedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = make_embedding_response(vector)
            client = EmbeddingClient(make_settings(), llm_api_key="sk-llm")
            result = await client.embed("hello world")
        assert result == vector

    async def test_uses_configured_model(self):
        with patch("memory.embedding.litellm.aembedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = make_embedding_response([0.0])
            client = EmbeddingClient(make_settings(model="text-embedding-ada-002"), llm_api_key="sk-llm")
            await client.embed("test")
        assert mock_embed.call_args.kwargs["model"] == "text-embedding-ada-002"

    async def test_uses_embedding_api_key_when_set(self):
        with patch("memory.embedding.litellm.aembedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = make_embedding_response([0.0])
            client = EmbeddingClient(make_settings(api_key="sk-embed"), llm_api_key="sk-llm")
            await client.embed("test")
        assert mock_embed.call_args.kwargs["api_key"] == "sk-embed"

    async def test_falls_back_to_llm_api_key_when_embedding_key_is_none(self):
        with patch("memory.embedding.litellm.aembedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = make_embedding_response([0.0])
            client = EmbeddingClient(make_settings(api_key=None), llm_api_key="sk-llm-fallback")
            await client.embed("test")
        assert mock_embed.call_args.kwargs["api_key"] == "sk-llm-fallback"

    async def test_passes_text_as_single_item_list(self):
        with patch("memory.embedding.litellm.aembedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = make_embedding_response([0.0])
            client = EmbeddingClient(make_settings(), llm_api_key="sk-llm")
            await client.embed("my query")
        assert mock_embed.call_args.kwargs["input"] == ["my query"]
