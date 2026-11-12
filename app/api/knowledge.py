"""Authenticated publication/rollback of prebuilt and evaluated knowledge versions."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.auth import Principal, ensure_roles, get_principal
from app.core.errors import ApiError, ErrorCode
from app.knowledge.contract import KnowledgeError
from app.knowledge.gaps import aggregate_gaps

router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])


class Activation(BaseModel):
    version: str
    expected_active_version: str | None
    reason: str = Field(min_length=1, max_length=1000)


def _service(request: Request):
    service = request.app.state.knowledge
    if service is None:
        raise ApiError(ErrorCode.KB_MODULE_MISSING, "知识库服务未启用")
    return service


@router.get("/{project}/status")
async def status(project: str, request: Request, baseline: str = "current_implementation",
                 principal: Principal = Depends(get_principal)):
    ensure_roles(principal, "reviewer", "kb_publisher")
    service = _service(request)
    release = await service.store.current(project, baseline)
    return {"project_id": project, "baseline": baseline,
            "active_version": release["version"] if release else None,
            "profile": release["profile"] if release else None,
            "history": await service.store.history(project)}


@router.post("/activate")
async def activate(body: Activation, request: Request, principal: Principal = Depends(get_principal)):
    ensure_roles(principal, "kb_publisher")
    service = _service(request)
    if not re.fullmatch(r"kb-runtime-[0-9a-f]{64}", body.version):
        raise ApiError(ErrorCode.INPUT_INVALID, "知识版本格式不正确")
    path = request.app.state.settings.knowledge_acceptance_dir / (body.version + ".json")
    if not path.is_file():
        raise ApiError(ErrorCode.INPUT_INVALID, "该版本缺少服务器验收记录")
    acceptance = json.loads(path.read_text(encoding="utf-8"))
    try:
        await service.publish(body.version, actor=principal.actor_id, reason=body.reason,
                              expected=body.expected_active_version, acceptance=acceptance,
                              allow_delegated=request.app.state.settings.knowledge_delegated_acceptance)
    except KnowledgeError as exc:
        raise ApiError(ErrorCode.DECISION_CONFLICT, str(exc)) from exc
    return {"active_version": body.version, "acceptance_scope": acceptance.get("release_scope")}


@router.get("/{project}/gaps")
async def gaps(project: str, request: Request, principal: Principal = Depends(get_principal)):
    ensure_roles(principal, "reviewer", "kb_publisher")
    return await aggregate_gaps(request.app.state.storage, project)
