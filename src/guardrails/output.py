from __future__ import annotations

from pydantic import BaseModel, ValidationError

from guardrails.input import GuardrailViolation


class OutputGuardrail:
    def validate(self, data: dict, schema: type[BaseModel]) -> BaseModel:
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            raise GuardrailViolation(
                f"Output failed schema validation: {exc}"
            ) from exc
