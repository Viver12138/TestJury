"""内存存储适配器：单测与 Mock 演示用，语义与 PostgreSQL 适配器保持一致。

关键点：
- `submit_review` 按 idempotency_key 串行化，保证同一 key 不产生双 active（ACC-CON-003）；
- `update_job`/`heartbeat` 校验 fencing token（ACC-M0-019 的内存等价物）；
- 投票 `(candidate_id, reviewer_id)` 首次为准，重复写入被忽略。
"""

from __future__ import annotations

import asyncio
import copy
from datetime import timedelta
from typing import Any

from app.core.budget import check_admission_costs
from app.core.errors import ApiError, ErrorCode
from app.core.state_machine import FencingMismatch
from app.storage.models import (
    AttachmentRecord,
    AuditRecord,
    BatchRecord,
    CandidateRecord,
    DecisionRecord,
    IssueRecord,
    ModelRunRecord,
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
        self._checkpoints: dict[tuple[str, str, str], dict] = {}
        self._candidates: dict[str, list[CandidateRecord]] = {}
        self._votes: dict[str, list[VoteRecord]] = {}
        self._model_runs: dict[str, list[ModelRunRecord]] = {}
        self._budget_reservations: dict[str, dict] = {}
        self._webhooks: dict[str, dict] = {}
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

    def _check_budget_admission(self, limits, batch_id=None):
        rows = list(self._budget_reservations.values())
        def cost(row):
            return row["cost_actual"] if row["status"] == "settled" else row["cost_reserved"]
        daily = sum(cost(row) for row in rows if row["budget_day"] == now().date().isoformat())
        batch = sum(cost(row) for row in rows if batch_id and row["batch_id"] == batch_id)
        check_admission_costs(daily, batch, limits)

    async def submit_review(self, job: ReviewJob, *, force: bool, budget_limits: dict | None = None) -> SubmitOutcome:
        async with self._lock(job.idempotency_key), self._global_lock:
            actives = [
                candidate
                for candidate in self._jobs.values()
                if candidate.idempotency_key == job.idempotency_key
                and candidate.superseded_by is None
            ]
            active = max(actives, key=lambda item: item.generation) if actives else None
            if budget_limits and (active is None or (force and active.is_terminal and active.input_hash == job.input_hash)):
                self._check_budget_admission(budget_limits, job.batch_id)

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
            self._checkpoints = {key: value for key, value in self._checkpoints.items() if key[0] != review_id}
            self._webhooks = {key: value for key, value in self._webhooks.items() if value["review_id"] != review_id}
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

    async def enqueue_webhooks(self) -> None:
        async with self._global_lock:
            for job in self._jobs.values():
                url = (job.request_payload.get("options") or {}).get("webhook_url")
                if not url or job.status not in {"done", "completed_with_warnings", "failed"}:
                    continue
                ident = f"{job.id}:review.{job.status}:{job.generation}"
                self._webhooks.setdefault(ident, {"event_id": ident, "review_id": job.id, "url": url,
                    "payload": {"review_id": job.id, "ai_verdict": job.ai_verdict,
                                "human_status": (job.report_json or {}).get("human_status", job.human_status),
                                "summary": job.report_summary or {}},
                    "status": "pending", "attempts": 0, "next_attempt_at": now(), "lease_until": None, "last_error": None})

    async def claim_webhook(self, lease_seconds: int, max_attempts: int) -> dict | None:
        async with self._global_lock:
            current = now()
            for row in self._webhooks.values():
                ready = ((row["status"] == "pending" and row["next_attempt_at"] <= current)
                         or (row["status"] == "sending" and row["lease_until"] <= current))
                if not ready:
                    continue
                if row["attempts"] >= max_attempts:
                    row.update(status="failed", last_error="retry_limit")
                    continue
                row.update(status="sending", attempts=row["attempts"] + 1,
                           lease_until=current + timedelta(seconds=lease_seconds))
                return copy.deepcopy(row)
            return None

    async def finish_webhook(self, event_id: str, attempt: int, success: bool, delay: int,
                             max_attempts: int, error: str | None) -> None:
        async with self._global_lock:
            row = self._webhooks.get(event_id)
            if row is not None and row["attempts"] == attempt and row["status"] == "sending":
                row.update(status="delivered" if success else "failed" if attempt >= max_attempts else "pending",
                           next_attempt_at=now() + timedelta(seconds=delay), lease_until=None, last_error=error)

    async def reserve_model_budget(self, review_id: str, fencing_token: int, reservation: dict, limits: dict) -> bool:
        async with self._global_lock:
            job = self._require_job(review_id)
            if job.fencing_token != fencing_token or job.status != "processing":
                raise FencingMismatch(fencing_token, job.fencing_token)
            rows = list(self._budget_reservations.values())
            own = [r for r in rows if r["review_id"] == review_id]
            batch = [r for r in rows if job.batch_id and r["batch_id"] == job.batch_id]
            daily = [r for r in rows if r["budget_day"] == now().date().isoformat()]

            def used(records, kind):
                return sum(r[kind + "_actual"] if r["status"] == "settled" else r[kind + "_reserved"] for r in records)

            if (used(own, "tokens") + reservation["tokens_reserved"] > limits["review_tokens"]
                    or used(own, "cost") + reservation["cost_reserved"] > limits["review_cost"]
                    or used(daily, "cost") + reservation["cost_reserved"] > limits["daily_cost"]
                    or (job.batch_id and used(batch, "cost") + reservation["cost_reserved"] > limits["batch_cost"])):
                return False
            self._budget_reservations[reservation["id"]] = {**reservation, "review_id": review_id, "batch_id": job.batch_id,
                "budget_day": now().date().isoformat(), "status": "reserved", "tokens_actual": None, "cost_actual": None}
            return True

    async def settle_model_budget(self, reservation_id: str, tokens: int, cost: float) -> None:
        async with self._global_lock:
            row = self._budget_reservations[reservation_id]
            if row["status"] == "reserved":
                row.update(status="settled", tokens_actual=tokens, cost_actual=cost)

    async def list_model_budget(self, review_id: str) -> list[dict]:
        return copy.deepcopy([r for r in self._budget_reservations.values() if r["review_id"] == review_id])

    async def get_checkpoint(self, review_id: str, key: str, input_digest: str) -> dict | None:
        return copy.deepcopy(self._checkpoints.get((review_id, key, input_digest)))

    async def put_checkpoint(self, review_id: str, key: str, input_digest: str,
                             payload: dict, output_digest: str, fencing_token: int) -> None:
        async with self._global_lock:
            job = self._require_job(review_id)
            if job.fencing_token != fencing_token or job.status != "processing":
                raise FencingMismatch(fencing_token, job.fencing_token)
            ident = (review_id, key, input_digest)
            existing = self._checkpoints.get(ident)
            if existing and existing["output_digest"] != output_digest:
                raise ValueError("checkpoint output is immutable")
            self._checkpoints.setdefault(ident, copy.deepcopy({"payload": payload, "output_digest": output_digest}))

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

    async def add_model_run(self, run: ModelRunRecord) -> None:
        self._model_runs.setdefault(run.review_id, []).append(run)

    async def list_model_runs(self, review_id: str) -> list[ModelRunRecord]:
        return list(self._model_runs.get(review_id, []))

    async def finalize_report(
        self,
        review_id: str,
        *,
        fencing_token: int,
        fields: dict[str, Any],
        issues: list[IssueRecord],
        review_tasks: list[ReviewTaskRecord] | None = None,
    ) -> ReviewJob:
        async with self._global_lock:
            job = self._require_job(review_id)
            if job.fencing_token != fencing_token:
                raise FencingMismatch(fencing_token, job.fencing_token)
            updated = job.with_fields(**fields)
            self._jobs[review_id] = updated
            self._issues[review_id] = list(issues)
            await self.create_review_tasks(review_tasks or [])
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

    async def create_batch(self, batch: BatchRecord, *, budget_limits: dict | None = None,
                           force: bool = False) -> BatchRecord:
        async with self._global_lock:
            if batch.idempotency_key:
                for existing in self._batches.values():
                    if existing.idempotency_key == batch.idempotency_key:
                        if force and budget_limits:
                            self._check_budget_admission(budget_limits, existing.id)
                        return existing
            if budget_limits:
                self._check_budget_admission(budget_limits, batch.id)
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
