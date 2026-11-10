"""人工复核任务 API（docs/03 §5.3）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query

from app.api.deps import get_principal, get_task_service
from app.core.auth import Principal, ensure_roles
from app.core.enums import Role
from app.services.tasks import ReviewTaskService

router = APIRouter(prefix="/v1", tags=["review-tasks"])


@router.get("/review-tasks")
async def list_tasks(
    status: str | None = Query(default=None),
    assignee: str | None = Query(default=None),
    principal: Principal = Depends(get_principal),
    service: ReviewTaskService = Depends(get_task_service),
):
    ensure_roles(principal, Role.REVIEWER, Role.APPROVER, Role.ADMIN)
    return {"items": await service.list(status=status, assignee=assignee)}


@router.get("/review-tasks/{task_id}")
async def get_task(
    task_id: str,
    principal: Principal = Depends(get_principal),
    service: ReviewTaskService = Depends(get_task_service),
):
    ensure_roles(principal, Role.REVIEWER, Role.APPROVER, Role.ADMIN)
    return await service.get(task_id)


@router.patch("/review-tasks/{task_id}")
async def update_task(
    task_id: str,
    payload: dict[str, Any] = Body(...),
    principal: Principal = Depends(get_principal),
    service: ReviewTaskService = Depends(get_task_service),
):
    ensure_roles(principal, Role.REVIEWER, Role.APPROVER)
    return await service.update(task_id, payload, actor_id=principal.actor_id)
