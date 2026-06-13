from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Literal, TypeVar

T = TypeVar("T")


class CircuitOpenError(Exception):
    pass


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
    ) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._failure_count = 0
        self._state: Literal["closed", "open", "half_open"] = "closed"
        self._opened_at: float | None = None

    @property
    def state(self) -> Literal["closed", "open", "half_open"]:
        return self._state

    async def call(self, fn: Callable[..., Awaitable[T]], *args: object) -> T:
        if self._state == "open":
            elapsed = time.monotonic() - (self._opened_at or 0.0)
            if elapsed < self._reset_timeout:
                raise CircuitOpenError(
                    f"Circuit '{self._name}' is open — try again in "
                    f"{self._reset_timeout - elapsed:.1f}s"
                )
            self._state = "half_open"

        try:
            result = await fn(*args)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        self._failure_count = 0
        self._state = "closed"
        self._opened_at = None

    def _on_failure(self) -> None:
        self._failure_count += 1
        if self._state == "half_open" or self._failure_count >= self._failure_threshold:
            self._state = "open"
            self._opened_at = time.monotonic()
