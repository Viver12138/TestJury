"""批量评审 API（docs/03 §4）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_batch_service, get_principal
from app.core.auth import Principal
from app.services.batches import BatchService

router = APIRouter(prefix="/v1", tags=["batches"])


@router.post("/review-batches")
async def create_batch(
    payload: dict[str, Any] = Body(...),
    principal: Principal = Depends(get_principal),
    service: BatchService = Depends(get_batch_service),
):
    status_code, body = await service.create(payload, principal)
    return JSONResponse(status_code=status_code, content=body)


@router.get("/review-batches/{batch_id}")
async def get_batch(
    batch_id: str,
    principal: Principal = Depends(get_principal),
    service: BatchService = Depends(get_batch_service),
):
    return await service.get(batch_id)
