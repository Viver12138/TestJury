"""人工复核任务服务（docs/03 §5.3、docs/09 §12）。

- 状态机与结果字段边界由 `core.state_machine` 与 docs/17 约束；
- PATCH 需要 `expected_version` 乐观锁；
- Issue 级结果必须带 reason；Report 级 `result` 必须为空。
"""

from __future__ import annotations

from typing import Any

from app.core.enums import IssueTaskResult, ReviewLevel, ReviewTaskStatus
from app.core.errors import ApiError, ErrorCode
from app.core.state_machine import IllegalTransition, check_review_task_transition
from app.storage.models import ReviewTaskRecord, now
from app.storage.port import Storage


class ReviewTaskService:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    async def list(
        self, *, status: str | None = None, assignee: str | None = None
    ) -> list[dict[str, Any]]:
        tasks = await self.storage.list_review_tasks(status=status, assignee=assignee)
        return [self._public(task) for task in tasks]

    async def get(self, task_id: str) -> dict[str, Any]:
        task = await self.storage.get_review_task(task_id)
        if task is None:
            raise ApiError(ErrorCode.NOT_FOUND, "复核任务不存在")
        return self._public(task)

    async def update(
        self,
        task_id: str,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        task = await self.storage.get_review_task(task_id)
        if task is None:
            raise ApiError(ErrorCode.NOT_FOUND, "复核任务不存在")
        expected_version = payload.get("expected_version")
        if not isinstance(expected_version, int):
            raise ApiError(
                ErrorCode.INPUT_INVALID, "expected_version 必填", field="expected_version"
            )
        target_status = payload.get("status")
        if target_status is not None and target_status != task.status:
            if target_status not in {item.value for item in ReviewTaskStatus}:
                raise ApiError(ErrorCode.INPUT_INVALID, "status 非法", field="status")
            try:
                check_review_task_transition(task.status, target_status)
            except IllegalTransition as exc:
                raise ApiError(ErrorCode.INVALID_DECISION_STATE, str(exc)) from exc

        changes: dict[str, Any] = {}
        if target_status is not None:
            changes["status"] = target_status
        if "assignee" in payload:
            changes["assignee"] = payload["assignee"]

        result = payload.get("result")
        if result is not None:
            if task.review_level == ReviewLevel.REPORT.value:
                raise ApiError(ErrorCode.INVALID_DECISION, "Report 级任务 result 必须为空")
            if result not in {item.value for item in IssueTaskResult}:
                raise ApiError(ErrorCode.INVALID_DECISION, "issue 级 result 非法")
            reason = payload.get("reason")
            if not reason or not str(reason).strip():
                raise ApiError(ErrorCode.INVALID_DECISION, "提交 result 必须提供 reason")
            changes["result"] = result
            changes["reason"] = str(reason).strip()
            changes["handled_at"] = now()
            if "status" not in changes:
                changes["status"] = ReviewTaskStatus.COMPLETED.value
                try:
                    check_review_task_transition(task.status, ReviewTaskStatus.COMPLETED.value)
                except IllegalTransition as exc:
                    raise ApiError(ErrorCode.INVALID_DECISION_STATE, str(exc)) from exc

        try:
            updated = await self.storage.update_review_task(
                task_id,
                expected_version=expected_version,
                actor_id=actor_id,
                **changes,
            )
        except ApiError:
            raise
        return self._public(updated)

    @staticmethod
    def _public(task: ReviewTaskRecord) -> dict[str, Any]:
        return {
            "task_id": task.id,
            "review_id": task.review_id,
            "issue_id": task.issue_id,
            "review_level": task.review_level,
            "priority": task.priority,
            "assignee": task.assignee,
            "status": task.status,
            "result": task.result,
            "reason": task.reason,
            "version": task.version,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "created_at": task.created_at.isoformat(),
        }
