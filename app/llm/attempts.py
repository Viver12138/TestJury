"""模型调用 attempts 的上下文收集。

`_complete()` 在每次真正发起供应商请求前写入一条 `started` 记录；外部
`asyncio.wait_for` 取消协程时，调用方仍能从上下文列表拿到已发生的尝试。
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

attempt_log: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "testjury_model_attempts", default=None
)
