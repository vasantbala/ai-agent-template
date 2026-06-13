from __future__ import annotations

import re

MAX_INPUT_LENGTH = 10_000

_INJECTION_PATTERNS = [
    re.compile(r"ignore (all )?(previous|prior|above) instructions", re.IGNORECASE),
    re.compile(r"you are now", re.IGNORECASE),
    re.compile(r"new (persona|role|instructions)", re.IGNORECASE),
    re.compile(r"</?(s|system|inst|instruction)>", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]", re.IGNORECASE),
    re.compile(r"disregard (your )?(previous|prior|all)", re.IGNORECASE),
]


class GuardrailViolation(Exception):
    pass


class InputGuardrail:
    def validate(self, text: str) -> None:
        if len(text) > MAX_INPUT_LENGTH:
            raise GuardrailViolation(
                f"Input exceeds maximum length of {MAX_INPUT_LENGTH} characters "
                f"(got {len(text)})"
            )
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                raise GuardrailViolation(
                    f"Input contains a disallowed pattern: '{pattern.pattern}'"
                )
