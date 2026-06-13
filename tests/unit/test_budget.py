from __future__ import annotations

import pytest

from reliability.budget import TokenBudget, BudgetExceededError


class TestTokenBudget:
    def test_starts_at_zero(self):
        b = TokenBudget(max_tokens=1000)
        assert b.used == 0

    def test_remaining_equals_max_initially(self):
        b = TokenBudget(max_tokens=1000)
        assert b.remaining == 1000

    def test_records_usage_correctly(self):
        b = TokenBudget(max_tokens=1000)
        b.record(100, 50)
        assert b.used == 150
        assert b.remaining == 850

    def test_accumulates_across_multiple_calls(self):
        b = TokenBudget(max_tokens=1000)
        b.record(100, 50)
        b.record(200, 100)
        assert b.used == 450
        assert b.remaining == 550

    def test_raises_on_budget_exceeded(self):
        b = TokenBudget(max_tokens=100)
        with pytest.raises(BudgetExceededError):
            b.record(60, 50)

    def test_raises_when_exactly_over(self):
        b = TokenBudget(max_tokens=100)
        with pytest.raises(BudgetExceededError):
            b.record(50, 51)

    def test_does_not_raise_at_exact_limit(self):
        b = TokenBudget(max_tokens=100)
        b.record(50, 50)
        assert b.used == 100
        assert b.remaining == 0

    def test_remaining_never_negative(self):
        b = TokenBudget(max_tokens=100)
        with pytest.raises(BudgetExceededError):
            b.record(200, 0)
        assert b.remaining == 0

    def test_budget_exceeded_error_message_includes_counts(self):
        b = TokenBudget(max_tokens=100)
        with pytest.raises(BudgetExceededError, match="110"):
            b.record(60, 50)
