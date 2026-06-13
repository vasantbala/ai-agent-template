from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from reliability.circuit_breaker import CircuitBreaker, CircuitOpenError


def make_cb(**kwargs) -> CircuitBreaker:
    return CircuitBreaker("test-server", **kwargs)


class TestCircuitBreaker:
    async def test_starts_closed(self):
        cb = make_cb()
        assert cb.state == "closed"

    async def test_successful_call_stays_closed(self):
        cb = make_cb()
        fn = AsyncMock(return_value="ok")
        result = await cb.call(fn)
        assert result == "ok"
        assert cb.state == "closed"

    async def test_opens_after_failure_threshold(self):
        cb = make_cb(failure_threshold=3)
        fn = AsyncMock(side_effect=RuntimeError("fail"))
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(fn)
        assert cb.state == "open"

    async def test_raises_immediately_when_open(self):
        cb = make_cb(failure_threshold=1, reset_timeout=60.0)
        fn = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(RuntimeError):
            await cb.call(fn)
        assert cb.state == "open"

        fn2 = AsyncMock(return_value="ok")
        with pytest.raises(CircuitOpenError):
            await cb.call(fn2)
        fn2.assert_not_awaited()

    async def test_transitions_to_half_open_after_timeout(self):
        cb = make_cb(failure_threshold=1, reset_timeout=1.0)
        fn_fail = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(RuntimeError):
            await cb.call(fn_fail)
        assert cb.state == "open"

        with patch("reliability.circuit_breaker.time.monotonic") as mock_time:
            mock_time.return_value = (cb._opened_at or 0.0) + 2.0
            fn_ok = AsyncMock(return_value="ok")
            result = await cb.call(fn_ok)

        assert result == "ok"
        assert cb.state == "closed"

    async def test_closes_on_half_open_success(self):
        cb = make_cb(failure_threshold=1, reset_timeout=0.0)
        fn_fail = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(RuntimeError):
            await cb.call(fn_fail)

        fn_ok = AsyncMock(return_value="recovered")
        result = await cb.call(fn_ok)
        assert result == "recovered"
        assert cb.state == "closed"
        assert cb._failure_count == 0

    async def test_reopens_on_half_open_failure(self):
        cb = make_cb(failure_threshold=1, reset_timeout=0.0)
        fn_fail = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(RuntimeError):
            await cb.call(fn_fail)

        fn_fail2 = AsyncMock(side_effect=RuntimeError("still failing"))
        with pytest.raises(RuntimeError):
            await cb.call(fn_fail2)

        assert cb.state == "open"

    async def test_does_not_open_below_threshold(self):
        cb = make_cb(failure_threshold=3)
        fn = AsyncMock(side_effect=RuntimeError("fail"))
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(fn)
        assert cb.state == "closed"

    async def test_passes_args_to_fn(self):
        cb = make_cb()
        fn = AsyncMock(return_value="result")
        await cb.call(fn, "a", "b")
        fn.assert_awaited_once_with("a", "b")
