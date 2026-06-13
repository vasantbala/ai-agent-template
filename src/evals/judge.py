from __future__ import annotations

import json
import re

from deepeval.models.base_model import DeepEvalBaseLLM

from config.settings import LLMSettings


def _extract_json(text: str) -> str:
    """Return the last valid JSON object found in text.

    Strips markdown fences first, then scans backwards for a matching
    { ... } pair. DeepEval's trimAndLoadJson uses the first { and last }
    which breaks when the model echoes JSON from the evaluated content in
    its reasoning — this finds the last self-contained JSON object instead.
    """
    text = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    end = len(text)
    while end > 0:
        last_close = text.rfind("}", 0, end)
        if last_close == -1:
            break
        depth = 0
        for i in range(last_close, -1, -1):
            if text[i] == "}":
                depth += 1
            elif text[i] == "{":
                depth -= 1
                if depth == 0:
                    candidate = text[i : last_close + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        break
        end = last_close
    return text


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
        return _extract_json(response.choices[0].message.content or "")

    async def a_generate(self, prompt: str, **kwargs) -> str:
        import litellm

        response = await litellm.acompletion(
            messages=[
                {"role": "system", "content": self._SYSTEM},
                {"role": "user", "content": prompt},
            ],
            **self._call_kwargs(),
        )
        return _extract_json(response.choices[0].message.content or "")
