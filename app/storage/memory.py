"""内存存储适配器：单测与 Mock 演示用，语义与 PostgreSQL 适配器保持一致。

关键点：
- `submit_review` 按 idempotency_key 串行化，保证同一 key 不产生双 active（ACC-CON-003）；
- `update_job`/`heartbeat` 校验 fencing token（ACC-M0-019 的内存等价物）；
- 投票 `(candidate_id, reviewer_id)` 首次为准，重复写入被忽略。
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from app.core.errors import ApiError, ErrorCode
from app.core.state_machine import FencingMismatch
from app.storage.models import (
    AttachmentRecord,
    AuditRecord,
    BatchRecord,
    CandidateRecord,
    DecisionRecord,
    IssueRecord,
    ReviewJob,
    ReviewTaskRecord,
    StageAttempt,
    StageRecord,
    VoteRecord,
    now,
)
from app.storage.port import SubmitOutcome


class MemoryStorage:
    def __init__(self, *, migration_version: str = "m0-memory") -> None:
        self._jobs: dict[str, ReviewJob] = {}
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._stages: dict[str, dict[str, StageRecord]] = {}
        self._attempts: dict[str, list[StageAttempt]] = {}
        self._candidates: dict[str, list[CandidateRecord]] = {}
        self._votes: dict[str, list[VoteRecord]] = {}
        self._issues: dict[str, list[IssueRecord]] = {}
        self._review_attachments: dict[str, dict[str, AttachmentRecord]] = {}
        self._decisions: dict[str, list[DecisionRecord]] = {}
        self._tasks: dict[str, ReviewTaskRecord] = {}
        self._task_events: dict[str, list[dict[str, Any]]] = {}
        self._batches: dict[str, BatchRecord] = {}
        self._attachments: dict[str, AttachmentRecord] = {}
        self._attachment_by_sha: dict[str, str] = {}
        self._audit: list[AuditRecord] = []
        self._migration_version = migration_version

    # ── 基础 ──

    def _lock(self, key: str) -> asyncio.Lock:
        if key not in self._key_locks:
            self._key_locks[key] = asyncio.Lock()
        return self._key_locks[key]

    def _require_job(self, review_id: str) -> ReviewJob:
        job = self._jobs.get(review_id)
        if job is None:
            raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")
        return job

    async def ping(self) -> bool:
        return True

    async def migration_version(self) -> str | None:
        return self._migration_version

    # ── 提交与任务 ──

    async def submit_review(self, job: ReviewJob, *, force: bool) -> SubmitOutcome:
        async with self._lock(job.idempotency_key):
            actives = [
                candidate
                for candidate in self._jobs.values()
                if candidate.idempotency_key == job.idempotency_key
                and candidate.superseded_by is None
            ]
            active = max(actives, key=lambda item: item.generation) if actives else None

            if active is not None:
                if active.input_hash != job.input_hash:
                    return SubmitOutcome(kind="conflict", job=active)
                if not force:
                    return SubmitOutcome(kind="replay", job=active)
                if not active.is_terminal:
                    return SubmitOutcome(kind="in_progress", job=active)

                generation = max(
                    item.generation
                    for item in self._jobs.values()
                    if item.idempotency_key == job.idempotency_key
                ) + 1
                job = job.with_fields(
                    generation=generation,
                    parent_review_id=active.id,
                    created_at=now(),
                )
                self._jobs[active.id] = active.with_fields(superseded_by=job.id)
            elif force:
                history = [
                    item.generation
                    for item in self._jobs.values()
                    if item.idempotency_key == job.idempotency_key
                ]
                job = job.with_fields(generation=(max(history) + 1) if history else 1)

            self._jobs[job.id] = job
            return SubmitOutcome(kind="created", job=job)

    async def get_job(self, review_id: str) -> ReviewJob | None:
        return self._jobs.get(review_id)

    async def delete_job(self, review_id: str) -> None:
        """合规删除（M0 最小实现）：幂等记录随记录删除，同键再提交视为新任务。"""

        async with self._global_lock:
            if self._jobs.pop(review_id, None) is None:
                raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")
            self._stages.pop(review_id, None)
            self._attempts.pop(review_id, None)
            self._candidates.pop(review_id, None)
            self._votes.pop(review_id, None)
            self._decisions.pop(review_id, None)
            self._issues.pop(review_id, None)
            self._review_attachments.pop(review_id, None)

    async def list_jobs(
        self,
        *,
        case_id: str | None = None,
        batch_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReviewJob]:
        jobs = sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)
        if case_id:
            jobs = [job for job in jobs if job.case_id == case_id]
        if batch_id:
            jobs = [job for job in jobs if job.batch_id == batch_id]
        return jobs[offset : offset + limit]

    async def update_job(
        self, review_id: str, *, fencing_token: int | None = None, **fields: Any
    ) -> ReviewJob:
        async with self._global_lock:
            job = self._require_job(review_id)
            if fencing_token is not None and job.fencing_token != fencing_token:
                raise FencingMismatch(fencing_token, job.fencing_token)
            updated = job.with_fields(**fields)
            self._jobs[review_id] = updated
            return updated

    async def claim_next_job(
        self, *, worker_id: str, lease_seconds: int
    ) -> ReviewJob | None:
        async with self._global_lock:
            current_time = now()
            candidates = [
                job
                for job in self._jobs.values()
                if job.status in ("queued", "retrying")
                or (
                    job.status == "processing"
                    and job.lease_expires_at is not None
                    and job.lease_expires_at <= current_time
                )
            ]
            if not candidates:
                return None
            job = min(candidates, key=lambda item: item.created_at)
            lease = timedelta(seconds=lease_seconds)
            updated = job.with_fields(
                status="processing",
                stage=job.stage or "input_check",
                attempt_count=job.attempt_count + 1,
                locked_by=worker_id,
                locked_at=current_time,
                lease_expires_at=current_time + lease,
                fencing_token=job.fencing_token + 1,
                started_at=job.started_at or current_time,
            )
            self._jobs[job.id] = updated
            return updated

    async def heartbeat(
        self, review_id: str, *, fencing_token: int, lease_seconds: int
    ) -> bool:
        async with self._global_lock:
            job = self._jobs.get(review_id)
            if job is None or job.fencing_token != fencing_token:
                return False
            self._jobs[review_id] = job.with_fields(
                lease_expires_at=now() + timedelta(seconds=lease_seconds)
            )
            return True

    async def release_job(
        self, review_id: str, *, fencing_token: int, error: str
    ) -> None:
        async with self._global_lock:
            job = self._require_job(review_id)
            if job.fencing_token != fencing_token:
                raise FencingMismatch(fencing_token, job.fencing_token)
            status = "failed" if job.attempt_count >= job.max_attempts else "retrying"
            self._jobs[review_id] = job.with_fields(
                status=status,
                last_error=error,
                error=error if status == "failed" else job.error,
                finished_at=now() if status == "failed" else None,
                lease_expires_at=None,
                locked_by=None,
            )

    async def queue_depth(self) -> int:
        return sum(
            1 for job in self._jobs.values() if job.status in ("queued", "retrying")
        )

    # ── 阶段 ──

    async def upsert_stage(self, stage: StageRecord) -> None:
        self._stages.setdefault(stage.review_id, {})[stage.stage] = stage

    async def list_stages(self, review_id: str) -> list[StageRecord]:
        return list(self._stages.get(review_id, {}).values())

    async def add_stage_attempt(self, attempt: StageAttempt) -> None:
        self._attempts.setdefault(attempt.review_id, []).append(attempt)

    async def list_stage_attempts(self, review_id: str) -> list[StageAttempt]:
        return list(self._attempts.get(review_id, []))

    # ── 候选与投票 ──

    async def replace_candidates(
        self, review_id: str, candidates: list[CandidateRecord]
    ) -> None:
        self._candidates[review_id] = list(candidates)
        self._votes[review_id] = []

    async def list_candidates(self, review_id: str) -> list[CandidateRecord]:
        return list(self._candidates.get(review_id, []))

    async def add_votes(self, review_id: str, votes: list[VoteRecord]) -> None:
        async with self._global_lock:
            existing = self._votes.setdefault(review_id, [])
            seen = {(vote.candidate_id, vote.reviewer_id) for vote in existing}
            for vote in votes:
                key = (vote.candidate_id, vote.reviewer_id)
                if key in seen:
                    continue
                seen.add(key)
                existing.append(vote)

    async def list_votes(self, review_id: str) -> list[VoteRecord]:
        return list(self._votes.get(review_id, []))

    async def finalize_report(
        self,
        review_id: str,
        *,
        fencing_token: int,
        fields: dict[str, Any],
        issues: list[IssueRecord],
    ) -> ReviewJob:
        async with self._global_lock:
            job = self._require_job(review_id)
            if job.fencing_token != fencing_token:
                raise FencingMismatch(fencing_token, job.fencing_token)
            updated = job.with_fields(**fields)
            self._jobs[review_id] = updated
            self._issues[review_id] = list(issues)
            return updated

    async def replace_issues(self, review_id: str, issues: list[IssueRecord]) -> None:
        self._issues[review_id] = list(issues)

    async def list_issues(self, review_id: str) -> list[IssueRecord]:
        return list(self._issues.get(review_id, []))

    async def bind_review_attachments(
        self, review_id: str, attachments: list[AttachmentRecord]
    ) -> None:
        bucket = self._review_attachments.setdefault(review_id, {})
        for attachment in attachments:
            bucket.setdefault(attachment.id, attachment)

    async def list_review_attachments(self, review_id: str) -> list[AttachmentRecord]:
        return list(self._review_attachments.get(review_id, {}).values())

    # ── 人工决定 ──

    async def add_decision(
        self,
        review_id: str,
        *,
        decision: str,
        reviewer_id: str,
        reason: str | None,
        report_schema_version: str,
        expected_updated_at: Any = None,
    ) -> DecisionRecord:
        async with self._global_lock:
            job = self._require_job(review_id)
            if expected_updated_at is not None and job.created_at != expected_updated_at:
                raise ApiError(ErrorCode.DECISION_CONFLICT, "报告已被修改，请重新拉取后再提交")
            history = self._decisions.setdefault(review_id, [])
            decision_no = (history[-1].decision_no + 1) if history else 1
            record = DecisionRecord(
                id=f"d-{review_id[:8]}-{decision_no}",
                review_id=review_id,
                decision_no=decision_no,
                decision=decision,
                reviewer_id=reviewer_id,
                reason=reason,
                previous_verdict=job.ai_verdict,
                previous_human_status=job.human_status,
                report_schema_version=report_schema_version,
            )
            history.append(record)
            human_status = {
                "approve": "approved",
                "reject": "rejected",
                "request_changes": "changes_requested",
            }[decision]
            self._jobs[review_id] = job.with_fields(
                human_status=human_status, current_decision_id=record.id
            )
            return record

    async def list_decisions(self, review_id: str) -> list[DecisionRecord]:
        return list(self._decisions.get(review_id, []))

    # ── 复核任务 ──

    async def create_review_tasks(self, tasks: list[ReviewTaskRecord]) -> None:
        for task in tasks:
            self._tasks[task.id] = task
            self._task_events.setdefault(task.id, []).append(
                {"action": "create", "actor": "system", "at": task.created_at}
            )

    async def list_review_tasks(
        self, *, status: str | None = None, assignee: str | None = None, limit: int = 100
    ) -> list[ReviewTaskRecord]:
        tasks = sorted(self._tasks.values(), key=lambda item: item.created_at, reverse=True)
        if status:
            tasks = [task for task in tasks if task.status == status]
        if assignee:
            tasks = [task for task in tasks if task.assignee == assignee]
        return tasks[:limit]

    async def get_review_task(self, task_id: str) -> ReviewTaskRecord | None:
        return self._tasks.get(task_id)

    async def update_review_task(
        self, task_id: str, *, expected_version: int, actor_id: str, **fields: Any
    ) -> ReviewTaskRecord:
        from dataclasses import replace

        async with self._global_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise ApiError(ErrorCode.NOT_FOUND, "复核任务不存在")
            if task.version != expected_version:
                raise ApiError(ErrorCode.DECISION_CONFLICT, "复核任务已被他人更新")
            updated = replace(task, version=task.version + 1, **fields)
            self._tasks[task_id] = updated
            self._task_events.setdefault(task_id, []).append(
                {"action": "update", "actor": actor_id, "fields": fields, "at": now()}
            )
            return updated

    # ── 批次 ──

    async def create_batch(self, batch: BatchRecord) -> BatchRecord:
        async with self._global_lock:
            if batch.idempotency_key:
                for existing in self._batches.values():
                    if existing.idempotency_key == batch.idempotency_key:
                        return existing
            self._batches[batch.id] = batch
            return batch

    async def get_batch(self, batch_id: str) -> BatchRecord | None:
        return self._batches.get(batch_id)

    async def update_batch(self, batch_id: str, **fields: Any) -> BatchRecord:
        from dataclasses import replace

        async with self._global_lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise ApiError(ErrorCode.NOT_FOUND, "批次不存在")
            updated = replace(batch, **fields)
            self._batches[batch_id] = updated
            return updated

    # ── 附件 ──

    async def add_attachment(self, attachment: AttachmentRecord) -> AttachmentRecord:
        async with self._global_lock:
            existing_id = self._attachment_by_sha.get(attachment.sha256)
            if existing_id:
                return self._attachments[existing_id]
            self._attachments[attachment.id] = attachment
            self._attachment_by_sha[attachment.sha256] = attachment.id
            return attachment

    async def get_attachment(self, attachment_id: str) -> AttachmentRecord | None:
        return self._attachments.get(attachment_id)

    # ── 审计 ──

    async def append_audit(self, record: AuditRecord) -> None:
        self._audit.append(record)

    async def list_audit(
        self, *, review_id: str | None = None, limit: int = 100
    ) -> list[AuditRecord]:
        records = list(reversed(self._audit))
        if review_id:
            records = [record for record in records if record.review_id == review_id]
        return records[:limit]
