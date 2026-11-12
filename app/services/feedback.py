"""Append-only issue feedback; identity and annotation provenance come from authentication."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.auth import Principal, ensure_roles
from app.core.errors import ApiError, ErrorCode
from app.storage.models import AuditRecord, new_id
from app.storage.port import Storage


class FeedbackItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    issue_no: int | None = Field(default=None, ge=1)
    verdict: Literal["adopted", "rejected", "missed"]
    note: str = Field(min_length=1, max_length=2000)
    step_index: int | None = Field(default=None, ge=1)
    severity: Literal["blocker", "major", "suggestion"] | None = None
    dimension: Literal["business", "test_design", "automation"] | None = None


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issues: list[FeedbackItem] = Field(min_length=1, max_length=100)


class FeedbackService:
    def __init__(self, storage: Storage):
        self.storage = storage

    async def submit(self, review_id: str, payload: dict, principal: Principal) -> dict:
        ensure_roles(principal, "reviewer", "approver")
        try:
            body = FeedbackInput.model_validate(payload)
        except ValidationError as exc:
            raise ApiError(ErrorCode.INPUT_INVALID, "反馈字段不合法") from exc
        job = await self.storage.get_job(review_id)
        if job is None:
            raise ApiError(ErrorCode.NOT_FOUND, "评审不存在")
        if not job.report_json or job.report_locked_at is None:
            raise ApiError(ErrorCode.INVALID_DECISION_STATE, "报告完成后才能反馈")
        numbers = {i["issue_no"] for i in job.report_json["issues"]}
        steps = len((job.normalized_case or job.request_payload.get("case", {})).get("steps", []))
        for item in body.issues:
            if not item.note.strip():
                raise ApiError(ErrorCode.INPUT_INVALID, "反馈说明不能为空")
            if item.verdict == "missed":
                if item.issue_no is not None or item.step_index is None or item.step_index > steps or item.severity is None:
                    raise ApiError(ErrorCode.INPUT_INVALID, "漏检反馈须指定有效步骤和严重级，不引用已有问题编号")
            elif item.issue_no not in numbers:
                raise ApiError(ErrorCode.INPUT_INVALID, "反馈的问题编号不属于本报告")
        feedback_id = new_id("feedback-")
        event = AuditRecord(id=feedback_id, event_type="issue_feedback", actor_id=principal.actor_id,
                            review_id=review_id, payload={
                                "feedback_id": feedback_id,
                                "actor_type": str(principal.actor_type),
                                "annotation_type": ("human_feedback" if str(principal.actor_type) == "human"
                                                    else "service_feedback"),
                                "issues": [item.model_dump(exclude_none=True) for item in body.issues],
                                "versions": job.report_json.get("versions", {}),
                                "gold_admission": "not_admitted",
                            })
        await self.storage.append_audit(event)
        return self.public(event)

    async def list(self, review_id: str, principal: Principal) -> dict:
        ensure_roles(principal, "reviewer", "approver")
        if await self.storage.get_job(review_id) is None:
            raise ApiError(ErrorCode.NOT_FOUND, "评审不存在")
        events = await self.storage.list_audit(review_id=review_id, limit=1000)
        return {"items": [self.public(e) for e in events if e.event_type == "issue_feedback"], "event_limit": 1000}

    @staticmethod
    def public(event: AuditRecord) -> dict:
        return {"feedback_id": event.id, "review_id": event.review_id, "reviewer": event.actor_id,
                "created_at": event.created_at.isoformat(), **event.payload}
