from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

TRANSIENT_EXCEPTIONS = (TimeoutError, ConnectionError, OSError)


async def retry_tool(
    fn: Callable[..., Awaitable[T]],
    *args: object,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> T:
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return await fn(*args)
        except TRANSIENT_EXCEPTIONS as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = min(base_delay * (2**attempt), max_delay)
                await asyncio.sleep(delay)
        except Exception:
            raise
    assert last_exc is not None
    raise last_exc
