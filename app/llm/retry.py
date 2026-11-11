"""重试策略：只重试可重试错误（超时/5xx/429/连接），4xx 与输出非法不重试。

docs/18 §3：
- 同一调用最多 3 次（1 次 + 2 次重试）；
- 指数退避 + 抖动，封顶 max_delay；
- 取消立即传播，不吞 CancelledError；
- 每次尝试通过 on_attempt 记录，供 model_runs 审计。
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.llm.base import AdapterError

T = TypeVar("T")

AttemptHook = Callable[[int, AdapterError | None, float], None]


async def call_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    jitter: float = 0.2,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_attempt: AttemptHook | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> T:
    """最多调用 `max_attempts` 次（默认 1 次 + 2 次重试）。"""

    if max_attempts < 1:
        raise ValueError("max_attempts 必须 >= 1")
    if base_delay < 0 or max_delay < 0 or not 0 <= jitter <= 1:
        raise ValueError("退避参数非法")
    last_error: AdapterError | None = None
    for attempt in range(1, max_attempts + 1):
        if is_cancelled is not None and is_cancelled():
            raise asyncio.CancelledError
        try:
            result = await operation()
        except asyncio.CancelledError:
            raise
        except AdapterError as exc:
            last_error = exc
            delay = 0.0
            if exc.retryable and attempt < max_attempts:
                raw = min(max_delay, base_delay * (2 ** (attempt - 1)))
                delay = raw + raw * jitter * random.random()
            if on_attempt is not None:
                on_attempt(attempt, exc, delay)
            if not exc.retryable or attempt >= max_attempts:
                raise
            await sleep(delay)
        else:
            if on_attempt is not None:
                on_attempt(attempt, None, 0.0)
            return result
    raise last_error  # pragma: no cover - 循环内必返回或抛出
