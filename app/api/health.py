"""健康检查与指标（docs/10 §11.0、docs/03 §7）。

- `/livez`：进程存活，不依赖 DB；
- `/readyz`：DB 连通、迁移版本可读；
- `/healthz`：兼容别名；
- `/metrics`：Prometheus 文本格式。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.enums import ReviewStatus

router = APIRouter(tags=["health"])


@router.get("/livez")
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    storage = request.app.state.storage
    checks: dict[str, str] = {}
    try:
        await storage.ping()
        checks["database"] = "ok"
        version = await storage.migration_version()
        checks["migration"] = version or "unknown"
    except Exception:  # pragma: no cover - 真实 DB 故障路径
        checks["database"] = "failed"
        return JSONResponse(status_code=503, content={"status": "unavailable", "checks": checks})

    queue_depth = await storage.queue_depth()
    checks["queue"] = "ok"
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "checks": checks, "queue_depth": queue_depth},
    )


@router.get("/healthz")
async def healthz(request: Request) -> JSONResponse:
    return await readyz(request)


@router.get("/metrics")
async def metrics(request: Request) -> Response:
    from app.core.observability import QUEUE_DEPTH, REVIEW_JOBS

    storage = request.app.state.storage
    try:
        QUEUE_DEPTH.set(await storage.queue_depth())
    except Exception:  # pragma: no cover
        pass
    for status in ReviewStatus:
        REVIEW_JOBS.labels(status=status.value)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
