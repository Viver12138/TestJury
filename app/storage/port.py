"""存储端口：服务层只依赖该协议，PostgreSQL 与内存实现可互换（tests 用内存）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

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
)


@dataclass
class SubmitOutcome:
    """提交结果：created（202）/ replay（200）/ conflict（422）/ in_progress（409）。"""

    kind: str
    job: ReviewJob


class Storage(Protocol):
    async def ping(self) -> bool: ...

    async def migration_version(self) -> str | None: ...

    async def submit_review(self, job: ReviewJob, *, force: bool) -> SubmitOutcome: ...

    async def get_job(self, review_id: str) -> ReviewJob | None: ...

    async def delete_job(self, review_id: str) -> None: ...

    async def list_jobs(
        self,
        *,
        case_id: str | None = None,
        batch_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReviewJob]: ...

    async def update_job(
        self, review_id: str, *, fencing_token: int | None = None, **fields: Any
    ) -> ReviewJob: ...

    async def claim_next_job(
        self, *, worker_id: str, lease_seconds: int
    ) -> ReviewJob | None: ...

    async def heartbeat(
        self, review_id: str, *, fencing_token: int, lease_seconds: int
    ) -> bool: ...

    async def release_job(self, review_id: str, *, fencing_token: int, error: str) -> None: ...

    async def queue_depth(self) -> int: ...

    async def upsert_stage(self, stage: StageRecord) -> None: ...

    async def list_stages(self, review_id: str) -> list[StageRecord]: ...

    async def add_stage_attempt(self, attempt: StageAttempt) -> None: ...

    async def list_stage_attempts(self, review_id: str) -> list[StageAttempt]: ...

    async def get_checkpoint(self, review_id: str, key: str, input_digest: str) -> dict | None: ...

    async def put_checkpoint(self, review_id: str, key: str, input_digest: str,
                             payload: dict, output_digest: str, fencing_token: int) -> None: ...

    async def replace_candidates(
        self, review_id: str, candidates: list[CandidateRecord]
    ) -> None: ...

    async def list_candidates(self, review_id: str) -> list[CandidateRecord]: ...

    async def add_votes(self, review_id: str, votes: list[VoteRecord]) -> None: ...

    async def list_votes(self, review_id: str) -> list[VoteRecord]: ...

    async def add_model_run(self, run: ModelRunRecord) -> None: ...

    async def list_model_runs(self, review_id: str) -> list[ModelRunRecord]: ...

    async def reserve_model_budget(self, review_id: str, fencing_token: int, reservation: dict, limits: dict) -> bool: ...

    async def settle_model_budget(self, reservation_id: str, tokens: int, cost: float) -> None: ...

    async def list_model_budget(self, review_id: str) -> list[dict]: ...

    async def enqueue_webhooks(self) -> None: ...

    async def claim_webhook(self, lease_seconds: int, max_attempts: int) -> dict | None: ...

    async def finish_webhook(self, event_id: str, attempt: int, success: bool, delay: int,
                             max_attempts: int, error: str | None) -> None: ...

    async def finalize_report(
        self,
        review_id: str,
        *,
        fencing_token: int,
        fields: dict[str, Any],
        issues: list[IssueRecord],
        review_tasks: list[ReviewTaskRecord] | None = None,
    ) -> ReviewJob: ...

    async def replace_issues(self, review_id: str, issues: list[IssueRecord]) -> None: ...

    async def list_issues(self, review_id: str) -> list[IssueRecord]: ...

    async def bind_review_attachments(
        self, review_id: str, attachments: list[AttachmentRecord]
    ) -> None: ...

    async def list_review_attachments(self, review_id: str) -> list[AttachmentRecord]: ...

    async def add_decision(
        self,
        review_id: str,
        *,
        decision: str,
        reviewer_id: str,
        reason: str | None,
        report_schema_version: str,
        expected_updated_at: datetime | None = None,
    ) -> DecisionRecord: ...

    async def list_decisions(self, review_id: str) -> list[DecisionRecord]: ...

    async def create_review_tasks(self, tasks: list[ReviewTaskRecord]) -> None: ...

    async def list_review_tasks(
        self, *, status: str | None = None, assignee: str | None = None, limit: int = 100
    ) -> list[ReviewTaskRecord]: ...

    async def get_review_task(self, task_id: str) -> ReviewTaskRecord | None: ...

    async def update_review_task(
        self, task_id: str, *, expected_version: int, actor_id: str, **fields: Any
    ) -> ReviewTaskRecord: ...

    async def create_batch(self, batch: BatchRecord) -> BatchRecord: ...

    async def get_batch(self, batch_id: str) -> BatchRecord | None: ...

    async def update_batch(self, batch_id: str, **fields: Any) -> BatchRecord: ...

    async def add_attachment(self, attachment: AttachmentRecord) -> AttachmentRecord: ...

    async def get_attachment(self, attachment_id: str) -> AttachmentRecord | None: ...

    async def append_audit(self, record: AuditRecord) -> None: ...

    async def list_audit(
        self, *, review_id: str | None = None, limit: int = 100
    ) -> list[AuditRecord]: ...
