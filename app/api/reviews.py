"""评审 API（docs/03 §1–§3）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.deps import get_decision_service, get_principal, get_review_service
from app.core.auth import Principal, ensure_roles
from app.core.enums import Role
from app.core.errors import ApiError, ErrorCode
from app.services.decisions import DecisionService
from app.services.reviews import ReviewService

router = APIRouter(prefix="/v1", tags=["reviews"])


@router.post("/reviews")
async def submit_review(
    request: Request,
    payload: dict[str, Any] = Body(...),
    principal: Principal = Depends(get_principal),
    service: ReviewService = Depends(get_review_service),
):
    result = await service.submit(payload, principal)
    return JSONResponse(status_code=result.status_code, content=result.body)


@router.get("/reviews")
async def list_reviews(
    case_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
    service: ReviewService = Depends(get_review_service),
):
    return {"items": await service.list_reviews(case_id=case_id, limit=limit)}


@router.get("/reviews/{review_id}")
async def get_review(
    review_id: str,
    principal: Principal = Depends(get_principal),
    service: ReviewService = Depends(get_review_service),
):
    return await service.get(review_id)


@router.get("/reviews/{review_id}/report")
async def get_report_markdown(
    review_id: str,
    principal: Principal = Depends(get_principal),
    service: ReviewService = Depends(get_review_service),
):
    markdown = await service.markdown(review_id)
    return PlainTextResponse(content=markdown, media_type="text/markdown; charset=utf-8")


@router.post("/reviews/{review_id}/decisions")
async def submit_decision(
    review_id: str,
    payload: dict[str, Any] = Body(...),
    principal: Principal = Depends(get_principal),
    service: DecisionService = Depends(get_decision_service),
):
    return await service.submit(review_id, payload, principal)


@router.get("/reviews/{review_id}/decisions")
async def list_decisions(
    review_id: str,
    principal: Principal = Depends(get_principal),
    service: DecisionService = Depends(get_decision_service),
):
    return {"items": await service.list(review_id)}


@router.post("/reviews/{review_id}/feedback")
async def submit_feedback(review_id: str, payload: dict[str, Any] = Body(...)):
    # M0 只保证接口存在且不误报成功；反馈实体与评测链路在 M5/M6 落地。
    raise ApiError(ErrorCode.NOT_FOUND, "反馈接口在 M0 未实现")


@router.delete("/reviews/{review_id}", status_code=204)
async def delete_review(
    review_id: str,
    principal: Principal = Depends(get_principal),
    service: ReviewService = Depends(get_review_service),
):
    ensure_roles(principal, Role.ADMIN)
    await service.delete(review_id, principal)
    return None
