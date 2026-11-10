"""请求上下文：request_id / trace_id 贯穿日志与错误响应。"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)

_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_TRACEPARENT = re.compile(r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


def new_request_id() -> str:
    return f"req-{uuid.uuid4().hex[:16]}"


def sanitize_incoming_id(value: str | None) -> str | None:
    """只接受安全字符集，避免把任意头内容写进日志/响应。"""
    if not value:
        return None
    candidate = value.strip()
    return candidate if _SAFE_ID.match(candidate) else None


def trace_id_from_headers(headers: dict[str, str], fallback: str) -> str:
    explicit = sanitize_incoming_id(headers.get("x-trace-id"))
    if explicit:
        return explicit
    traceparent = (headers.get("traceparent") or "").strip()
    match = _TRACEPARENT.match(traceparent)
    if match:
        return match.group(3)
    return fallback


def set_request_context(request_id: str, trace_id: str) -> None:
    _request_id.set(request_id)
    _trace_id.set(trace_id)


def clear_request_context() -> None:
    _request_id.set(None)
    _trace_id.set(None)


def get_request_id() -> str:
    return _request_id.get() or new_request_id()


def get_trace_id() -> str:
    return _trace_id.get() or get_request_id()
