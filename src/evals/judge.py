from __future__ import annotations

from deepeval.models.base_model import DeepEvalBaseLLM

from config.settings import LLMSettings


def _model_string(settings: LLMSettings) -> str:
    provider = settings.provider
    model = settings.model
    if provider == "openai":
        return model
    if provider == "anthropic":
        return f"anthropic/{model}"
    if provider == "openrouter":
        return f"openrouter/{model}"
    return model


class LiteLLMJudge(DeepEvalBaseLLM):
    """DeepEval-compatible judge model backed by LiteLLM.

    Reuses the project's configured LLM credentials so no separate
    OPENAI_API_KEY is required when using Anthropic or OpenRouter.
    """

    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings
        # Skip DeepEvalBaseLLM.__init__ — it calls load_model() which
        # tries to validate OpenAI creds before we can set _settings.
        self.name = settings.model

    def load_model(self):
        return self

    def get_model_name(self) -> str:
        return self._settings.model

    # Instruct the judge to output only JSON so trimAndLoadJson never
    # picks up JSON fragments from the evaluated content in the reasoning.
    _SYSTEM = "You are an evaluation assistant. Respond with ONLY a valid JSON object — no preamble, no explanation, no markdown."

    def _call_kwargs(self) -> dict:
        kwargs = {
            "model": _model_string(self._settings),
            "api_key": self._settings.api_key,
            "max_tokens": 1024,
            "temperature": 0.0,
        }
        if self._settings.base_url:
            kwargs["base_url"] = self._settings.base_url
        return kwargs

    def generate(self, prompt: str, **kwargs) -> str:
        import litellm

        response = litellm.completion(
            messages=[
                {"role": "system", "content": self._SYSTEM},
                {"role": "user", "content": prompt},
            ],
            **self._call_kwargs(),
        )
        return response.choices[0].message.content or ""

    async def a_generate(self, prompt: str, **kwargs) -> str:
        import litellm

        response = await litellm.acompletion(
            messages=[
                {"role": "system", "content": self._SYSTEM},
                {"role": "user", "content": prompt},
            ],
            **self._call_kwargs(),
        )
        return response.choices[0].message.content or ""
