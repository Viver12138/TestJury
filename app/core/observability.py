"""可观测性：请求上下文中间件、访问日志与 Prometheus 指标（docs/10 §11.0）。

指标口径（M0 只要求存在且可查询，压测门槛在 M 后续阶段定）：
- HTTP 请求计数与延迟（按 method/path/status）
- 阶段执行耗时与失败计数（stage/status/error_code）
- 任务终态计数、队列深度
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import structlog
from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import (
    clear_request_context,
    get_request_id,
    get_trace_id,
    new_request_id,
    sanitize_incoming_id,
    set_request_context,
    trace_id_from_headers,
)

logger = structlog.get_logger("testjury.http")

HTTP_REQUESTS = Counter(
    "testjury_http_requests_total",
    "HTTP 请求总数",
    ["method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "testjury_http_request_duration_seconds",
    "HTTP 请求耗时",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
STAGE_DURATION = Histogram(
    "testjury_stage_duration_seconds",
    "评审阶段耗时",
    ["stage", "status"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 240.0),
)
STAGE_FAILURES = Counter(
    "testjury_stage_failures_total",
    "评审阶段失败次数",
    ["stage", "error_code"],
)
REVIEW_JOBS = Counter(
    "testjury_review_jobs_total",
    "评审任务终态计数",
    ["status"],
)
QUEUE_DEPTH = Gauge(
    "testjury_queue_depth",
    "队列中等待执行的任务数",
)
RUNNING_JOBS = Gauge(
    "testjury_reviews_running",
    "当前正在执行的评审任务数",
)


def observe_stage(stage: str, status: str, duration_seconds: float) -> None:
    STAGE_DURATION.labels(stage=stage, status=status).observe(duration_seconds)
    if status == "failed":
        STAGE_FAILURES.labels(stage=stage, error_code="UNKNOWN").inc()


def record_stage_failure(stage: str, error_code: str) -> None:
    STAGE_FAILURES.labels(stage=stage, error_code=error_code).inc()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers
        request_id = sanitize_incoming_id(incoming.get("x-request-id")) or new_request_id()
        trace_id = trace_id_from_headers(dict(incoming), request_id)
        set_request_context(request_id, trace_id)
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
        )
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            elapsed = time.perf_counter() - started
            route = request.scope.get("route")
            path_template = getattr(route, "path", request.url.path)
            logger.info(
                "http_request",
                status=status_code,
                duration_ms=round(elapsed * 1000, 2),
                path_template=path_template,
                request_id=get_request_id(),
                trace_id=get_trace_id(),
            )
            HTTP_REQUESTS.labels(
                method=request.method, path=path_template, status=str(status_code)
            ).inc()
            HTTP_LATENCY.labels(method=request.method, path=path_template).observe(elapsed)
            structlog.contextvars.clear_contextvars()
            clear_request_context()

        response.headers["X-Request-Id"] = request_id
        response.headers["X-Trace-Id"] = trace_id
        return response
