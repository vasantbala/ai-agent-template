import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import BaseModel

from config.settings import LLMSettings
from llm.client import LLMClient


def make_settings(**overrides) -> LLMSettings:
    defaults = {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "api_key": "sk-test",
    }
    return LLMSettings(**(defaults | overrides))


def make_mock_response(content: str = "Hello") -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = None
    response = MagicMock()
    response.choices = [choice]
    response.usage.prompt_tokens = 10
    response.usage.completion_tokens = 5
    response.usage.total_tokens = 15
    return response


class TestModelString:
    def test_anthropic_prefixed(self):
        client = LLMClient(make_settings(provider="anthropic", model="claude-sonnet-4-6"))
        assert client._model_string() == "anthropic/claude-sonnet-4-6"

    def test_openai_no_prefix(self):
        client = LLMClient(make_settings(provider="openai", model="gpt-4o"))
        assert client._model_string() == "gpt-4o"

    def test_openrouter_prefixed(self):
        client = LLMClient(make_settings(provider="openrouter", model="anthropic/claude-sonnet-4-6"))
        assert client._model_string() == "openrouter/anthropic/claude-sonnet-4-6"


class TestBaseKwargs:
    def test_includes_required_fields(self):
        client = LLMClient(make_settings())
        kwargs = client._base_kwargs()
        assert "model" in kwargs
        assert kwargs["api_key"] == "sk-test"
        assert kwargs["max_tokens"] == 4096
        assert kwargs["temperature"] == 0.0

    def test_base_url_excluded_when_none(self):
        client = LLMClient(make_settings())
        kwargs = client._base_kwargs()
        assert "base_url" not in kwargs

    def test_base_url_included_when_set(self):
        client = LLMClient(make_settings(base_url="https://openrouter.ai/api/v1"))
        kwargs = client._base_kwargs()
        assert kwargs["base_url"] == "https://openrouter.ai/api/v1"


class TestComplete:
    @pytest.fixture
    def mock_acompletion(self):
        with patch("llm.client.litellm.acompletion", new_callable=AsyncMock) as mock:
            mock.return_value = make_mock_response("Test response")
            yield mock

    async def test_passes_messages(self, mock_acompletion):
        client = LLMClient(make_settings())
        messages = [{"role": "user", "content": "Hello"}]
        await client.complete(messages)
        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["messages"] == messages

    async def test_passes_correct_model(self, mock_acompletion):
        client = LLMClient(make_settings())
        await client.complete([{"role": "user", "content": "Hi"}])
        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["model"] == "anthropic/claude-sonnet-4-6"

    async def test_tools_included_when_provided(self, mock_acompletion):
        client = LLMClient(make_settings())
        tools = [{"type": "function", "function": {"name": "search", "description": "Search", "parameters": {}}}]
        await client.complete([{"role": "user", "content": "search for X"}], tools=tools)
        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["tools"] == tools
        assert call_kwargs["tool_choice"] == "auto"

    async def test_tools_excluded_when_none(self, mock_acompletion):
        client = LLMClient(make_settings())
        await client.complete([{"role": "user", "content": "Hi"}])
        call_kwargs = mock_acompletion.call_args.kwargs
        assert "tools" not in call_kwargs

    async def test_response_format_passed_when_set(self, mock_acompletion):
        class MySchema(BaseModel):
            answer: str

        client = LLMClient(make_settings())
        await client.complete([{"role": "user", "content": "Hi"}], response_format=MySchema)
        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["response_format"] is MySchema

    async def test_returns_response_object(self, mock_acompletion):
        client = LLMClient(make_settings())
        result = await client.complete([{"role": "user", "content": "Hi"}])
        assert result is not None
        assert result.choices[0].message.content == "Test response"
