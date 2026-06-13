from __future__ import annotations


class BudgetExceededError(Exception):
    pass


class TokenBudget:
    def __init__(self, max_tokens: int) -> None:
        self._max = max_tokens
        self._used = 0

    def record(self, prompt_tokens: int, completion_tokens: int) -> None:
        self._used += prompt_tokens + completion_tokens
        if self._used > self._max:
            raise BudgetExceededError(
                f"Token budget exceeded: used {self._used}, limit {self._max}"
            )

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return max(0, self._max - self._used)
