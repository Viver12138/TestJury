"""报告级人工决定（append-only，docs/03 §5.2、docs/09 §4）。

- 只 INSERT；`human_status` 由最新 `decision_no` 派生；
- 仅 `approver` 可 approve/reject，`reviewer` 只能 request_changes；
- 系统身份（actor_type=service）不得审批；
- 审批人 ≠ 提交人（可配置）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.config import Settings
from app.core.auth import (
    Principal,
    ensure_approval_allowed,
    ensure_approval_separation,
)
from app.core.enums import DecisionValue, HumanStatus
from app.core.errors import ApiError, ErrorCode
from app.storage.models import AuditRecord, DecisionRecord, new_id
from app.storage.port import Storage

HUMAN_STATUS_BY_DECISION = {
    DecisionValue.APPROVE.value: HumanStatus.APPROVED.value,
    DecisionValue.REJECT.value: HumanStatus.REJECTED.value,
    DecisionValue.REQUEST_CHANGES.value: HumanStatus.CHANGES_REQUESTED.value,
}


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApiError(ErrorCode.INPUT_INVALID, "expected_updated_at 不是合法时间", field="expected_updated_at") from exc


class DecisionService:
    def __init__(self, storage: Storage, settings: Settings) -> None:
        self.storage = storage
        self.settings = settings

    async def submit(
        self,
        review_id: str,
        payload: dict[str, Any],
        principal: Principal,
    ) -> dict[str, Any]:
        decision = str(payload.get("decision", "")).strip()
        if decision not in {item.value for item in DecisionValue}:
            raise ApiError(ErrorCode.INVALID_DECISION, "decision 必须是 approve/reject/request_changes")
        reason = payload.get("reason")
        if decision in (DecisionValue.REJECT.value, DecisionValue.REQUEST_CHANGES.value):
            if not reason or not str(reason).strip():
                raise ApiError(
                    ErrorCode.INVALID_DECISION,
                    "reject / request_changes 必须提供 reason",
                    field="reason",
                )

        ensure_approval_allowed(principal, decision)

        job = await self.storage.get_job(review_id)
        if job is None:
            raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")
        if not job.report_json:
            raise ApiError(ErrorCode.INVALID_DECISION_STATE, "报告尚未生成，不能审批")
        if job.report_locked_at is None:
            raise ApiError(ErrorCode.INVALID_DECISION_STATE, "报告未锁定，不能审批")

        if (
            self.settings.decision_require_separation
            and job.submitter_id is not None
            and principal.actor_id == job.submitter_id
        ):
            await self.storage.append_audit(
                AuditRecord(
                    id=new_id("a-"),
                    event_type="decision_rejected",
                    actor_id=principal.actor_id,
                    review_id=review_id,
                    payload={"reason": "self_approval_forbidden"},
                )
            )
        ensure_approval_separation(principal, job.submitter_id, self.settings)

        history = await self.storage.list_decisions(review_id)
        if history:
            latest = history[-1]
            if latest.decision == decision and (latest.reason or "") == (reason or ""):
                raise ApiError(ErrorCode.DECISION_CONFLICT, "重复提交同一人工决定")

        expected = _parse_timestamp(payload.get("expected_updated_at"))
        record = await self.storage.add_decision(
            review_id,
            decision=decision,
            reviewer_id=principal.actor_id,
            reason=str(reason).strip() if reason else None,
            report_schema_version=job.report_schema_version,
            expected_updated_at=expected,
        )
        await self.storage.append_audit(
            AuditRecord(
                id=new_id("a-"),
                event_type="decision",
                actor_id=principal.actor_id,
                review_id=review_id,
                payload={"decision": decision, "decision_no": record.decision_no},
            )
        )
        return self._public(record)

    async def list(self, review_id: str) -> list[dict[str, Any]]:
        job = await self.storage.get_job(review_id)
        if job is None:
            raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")
        history = await self.storage.list_decisions(review_id)
        return [self._public(record) for record in history]

    @staticmethod
    def _public(record: DecisionRecord) -> dict[str, Any]:
        return {
            "decision_no": record.decision_no,
            "decision": record.decision,
            "reviewer_id": record.reviewer_id,
            "reason": record.reason,
            "human_status": HUMAN_STATUS_BY_DECISION[record.decision],
            "report_schema_version": record.report_schema_version,
            "created_at": record.created_at.isoformat(),
        }
