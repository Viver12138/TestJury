"""领域记录：服务层与存储适配器共享的数据结构（非 ORM）。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str = "") -> str:
    value = str(uuid4())
    return f"{prefix}{value}" if prefix else value


@dataclass
class ReviewJob:
    id: str
    case_id: str
    case_version: int
    module: str | None
    test_type: str
    test_type_source: str
    status: str
    stage: str | None
    input_hash: str
    idempotency_key: str
    request_payload: dict[str, Any]
    report_schema_version: str
    generation: int = 1
    parent_review_id: str | None = None
    superseded_by: str | None = None
    batch_id: str | None = None
    case_title: str | None = None
    ai_verdict: str | None = None
    human_status: str = "pending"
    current_decision_id: str | None = None
    degraded: bool = False
    degraded_reasons: list[str] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    topology: str = "multi"
    topology_snapshot: dict[str, Any] = field(default_factory=dict)
    review_completeness: dict[str, Any] = field(default_factory=dict)
    input_quality: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, Any] = field(default_factory=dict)
    test_scope: dict[str, Any] | None = None
    automation_context: dict[str, Any] | None = None
    kb_content_version: str | None = None
    kb_build_version: str | None = None
    rubric_version: str | None = None
    prompt_versions: dict[str, Any] = field(default_factory=dict)
    prompt_version_hash: str = ""
    retrieval_config_version: str | None = None
    embedding_profile_id: int | None = None
    reranker_profile_id: int | None = None
    model_config_version: str | None = None
    normalized_case: dict[str, Any] | None = None
    report_summary: dict[str, Any] | None = None
    report_json: dict[str, Any] | None = None
    report_locked_at: datetime | None = None
    error: str | None = None
    attempt_count: int = 0
    max_attempts: int = 3
    locked_by: str | None = None
    locked_at: datetime | None = None
    lease_expires_at: datetime | None = None
    fencing_token: int = 0
    last_error: str | None = None
    submitter_id: str | None = None
    created_at: datetime = field(default_factory=now)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def with_fields(self, **changes: Any) -> ReviewJob:
        return replace(self, **changes)

    @property
    def is_terminal(self) -> bool:
        return self.status in {"done", "completed_with_warnings", "failed", "cancelled"}


@dataclass
class StageRecord:
    review_id: str
    stage: str
    status: str = "pending"
    attempt: int = 1
    fencing_token: int | None = None
    input_digest: str | None = None
    output_ref: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


@dataclass
class StageAttempt:
    review_id: str
    stage: str
    attempt_no: int
    status: str
    fencing_token: int | None = None
    input_digest: str | None = None
    output_ref: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    worker_id: str | None = None
    model_run_id: str | None = None


@dataclass
class CandidateRecord:
    id: str
    review_id: str
    candidate_no: int
    dimension: str
    standardized_text: str
    step_index: int | None = None
    severity_proposal: str | None = None
    claims: list[dict[str, Any]] = field(default_factory=list)
    evidence_status: str = "insufficient"
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    proposed_by: list[str] = field(default_factory=list)
    merged_from: list[dict[str, Any]] = field(default_factory=list)
    fusion_basis: dict[str, Any] = field(default_factory=dict)
    status: str = "candidate"
    vote_valid_count: int = 0
    vote_completeness: str | None = None
    category: str | None = None


@dataclass
class VoteRecord:
    id: str
    review_id: str
    candidate_id: str
    reviewer_id: str
    validity: str
    severity: str | None = None
    reason: str | None = None
    model_run_id: str | None = None
    created_at: datetime = field(default_factory=now)


@dataclass
class IssueRecord:
    """`issues` 投影行：从 `report_json.issues` 派生，不是事实源。"""

    review_id: str
    issue_no: int
    dimension: str
    severity: str
    category: str
    rationale: str
    status: str
    step_index: int | None = None
    candidate_id: str | None = None
    evidence_quote: str | None = None
    suggestion: str | None = None
    kb_grounded: bool = False
    kb_refs: list[Any] = field(default_factory=list)
    evidence_refs: list[Any] = field(default_factory=list)
    evidence_type: str | None = None
    evidence_strength: str | None = None
    evidence_status: str | None = None
    proposed_by: list[Any] = field(default_factory=list)
    confidence: float | None = None
    confidence_source: str = "uncalibrated"
    model_confidence: float | None = None
    validation_status: str | None = None
    evidence_support_status: str | None = None
    decision_status: str | None = None
    chief_decision: str | None = None
    chief_reason: str | None = None
    human_verdict: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class DecisionRecord:
    id: str
    review_id: str
    decision_no: int
    decision: str
    reviewer_id: str
    reason: str | None = None
    previous_verdict: str | None = None
    previous_human_status: str | None = None
    report_schema_version: str = "report-1.0"
    created_at: datetime = field(default_factory=now)


@dataclass
class ReviewTaskRecord:
    id: str
    review_id: str
    review_level: str
    priority: str = "normal"
    issue_id: str | None = None
    assignee: str | None = None
    status: str = "pending"
    result: str | None = None
    reason: str | None = None
    source: str = "auto"
    due_at: datetime | None = None
    version: int = 0
    created_at: datetime = field(default_factory=now)
    started_at: datetime | None = None
    handled_at: datetime | None = None


@dataclass
class AttachmentRecord:
    id: str
    file_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    storage_uri: str
    storage_path: str | None = None
    uploader_id: str | None = None
    status: str = "ready"
    created_at: datetime = field(default_factory=now)


@dataclass
class BatchRecord:
    id: str
    status: str = "queued"
    total: int = 0
    done: int = 0
    failed: int = 0
    caller_id: str | None = None
    input_hash: str | None = None
    idempotency_key: str | None = None
    created_at: datetime = field(default_factory=now)
    finished_at: datetime | None = None


@dataclass
class AuditRecord:
    id: str
    event_type: str
    actor_id: str | None
    review_id: str | None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=now)
