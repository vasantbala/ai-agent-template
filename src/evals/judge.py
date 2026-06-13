from __future__ import annotations

from deepeval.models.base_model import DeepEvalBaseLLM

from config.settings import LLMSettings


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

    def generate(self, prompt: str, **kwargs) -> str:
        import litellm

        s = self._settings
        response = litellm.completion(
            model=s.model,
            messages=[{"role": "user", "content": prompt}],
            api_key=s.api_key,
            base_url=s.base_url,
            max_tokens=1024,
            temperature=0.0,
        )
        return response.choices[0].message.content or ""

    async def a_generate(self, prompt: str, **kwargs) -> str:
        import litellm

        s = self._settings
        response = await litellm.acompletion(
            model=s.model,
            messages=[{"role": "user", "content": prompt}],
            api_key=s.api_key,
            base_url=s.base_url,
            max_tokens=1024,
            temperature=0.0,
        )
        return response.choices[0].message.content or ""
