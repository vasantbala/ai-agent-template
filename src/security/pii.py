from __future__ import annotations

import re

from config.settings import PiiConfig

_PATTERNS: dict[str, str] = {
    "email":       r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    "phone":       r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ssn":         r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d[ -]?){13,16}\b",
    "ip_address":  r"\b\d{1,3}(?:\.\d{1,3}){3}\b",
}


class PiiScrubber:
    def __init__(self, config: PiiConfig) -> None:
        self._enabled = config.enabled
        self._replacement = config.replacement
        self._patterns = [
            re.compile(_PATTERNS[p])
            for p in config.patterns
            if p in _PATTERNS
        ]

    def scrub(self, text: str) -> str:
        if not self._enabled:
            return text
        for pattern in self._patterns:
            text = pattern.sub(self._replacement, text)
        return text
