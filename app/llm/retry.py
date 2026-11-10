"""重试策略：只重试可重试错误（超时/5xx/429/连接），4xx 与输出非法不重试。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.llm.base import AdapterError

T = TypeVar("T")


async def call_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """最多调用 `max_attempts` 次（默认 1 次 + 2 次重试）。"""

    if max_attempts < 1:
        raise ValueError("max_attempts 必须 >= 1")
    last_error: AdapterError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except AdapterError as exc:
            last_error = exc
            if not exc.retryable or attempt >= max_attempts:
                raise
            await sleep(base_delay * (2 ** (attempt - 1)))
    raise last_error  # pragma: no cover - 循环内必返回或抛出
