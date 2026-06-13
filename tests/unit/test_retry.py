from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from reliability.retry import retry_tool, TRANSIENT_EXCEPTIONS


class TestRetryTool:
    async def test_succeeds_on_first_try(self):
        fn = AsyncMock(return_value="ok")
        result = await retry_tool(fn, max_attempts=3, base_delay=0.0)
        assert result == "ok"
        fn.assert_awaited_once()

    async def test_succeeds_on_second_try_after_transient_failure(self):
        fn = AsyncMock(side_effect=[ConnectionError("down"), "ok"])
        with patch("reliability.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await retry_tool(fn, max_attempts=3, base_delay=1.0)
        assert result == "ok"
        assert fn.await_count == 2
        mock_sleep.assert_awaited_once_with(1.0)  # base_delay * 2^0

    async def test_raises_after_max_attempts(self):
        fn = AsyncMock(side_effect=TimeoutError("timeout"))
        with patch("reliability.retry.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(TimeoutError):
                await retry_tool(fn, max_attempts=3, base_delay=0.0)
        assert fn.await_count == 3

    async def test_non_transient_error_not_retried(self):
        fn = AsyncMock(side_effect=ValueError("bad args"))
        with pytest.raises(ValueError):
            await retry_tool(fn, max_attempts=3, base_delay=0.0)
        fn.assert_awaited_once()

    async def test_backoff_grows_exponentially(self):
        fn = AsyncMock(side_effect=[ConnectionError(), ConnectionError(), "ok"])
        with patch("reliability.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await retry_tool(fn, max_attempts=3, base_delay=1.0)
        delays = [call.args[0] for call in mock_sleep.await_args_list]
        assert delays == [1.0, 2.0]  # base * 2^0, base * 2^1

    async def test_backoff_capped_at_max_delay(self):
        fn = AsyncMock(side_effect=[ConnectionError(), ConnectionError(), "ok"])
        with patch("reliability.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await retry_tool(fn, max_attempts=3, base_delay=10.0, max_delay=15.0)
        delays = [call.args[0] for call in mock_sleep.await_args_list]
        assert delays[0] == 10.0   # 10 * 2^0 = 10, under cap
        assert delays[1] == 15.0   # 10 * 2^1 = 20, capped to 15

    async def test_passes_args_to_fn(self):
        fn = AsyncMock(return_value="result")
        await retry_tool(fn, "arg1", "arg2", max_attempts=1)
        fn.assert_awaited_once_with("arg1", "arg2")

    async def test_oserror_is_retried(self):
        fn = AsyncMock(side_effect=[OSError("io error"), "ok"])
        with patch("reliability.retry.asyncio.sleep", new_callable=AsyncMock):
            result = await retry_tool(fn, max_attempts=3, base_delay=0.0)
        assert result == "ok"
