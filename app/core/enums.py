"""全局枚举：唯一来源 docs/17（全局数据字典）。

规则：
- 新增/删除枚举值必须同步 docs/17、数据库 CHECK、API Schema、Prompt 与验收用例。
- `tests/contract/test_enums.py` 会解析 docs/17 与本文件逐项比对，禁止手工复制同步。
"""

from __future__ import annotations

from enum import StrEnum


class ReviewStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    RETRYING = "retrying"
    DONE = "done"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_REVIEW_STATUSES = frozenset(
    {ReviewStatus.DONE, ReviewStatus.COMPLETED_WITH_WARNINGS, ReviewStatus.FAILED, ReviewStatus.CANCELLED}
)


class TestType(StrEnum):
    FUNCTIONAL = "functional"
    PERFORMANCE = "performance"
    SECURITY = "security"
    COMPATIBILITY = "compatibility"
    RELIABILITY = "reliability"
    USABILITY = "usability"
    OTHER = "other"


V1_SUPPORTED_TEST_TYPES = frozenset({TestType.FUNCTIONAL})


class TestTypeSource(StrEnum):
    REQUEST = "request"
    COMPAT_DEFAULT = "compat_default"


class BatchStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AiVerdict(StrEnum):
    BLOCKED = "blocked"
    CONDITIONAL = "conditional"
    NEED_HUMAN = "need_human"


class HumanStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class DecisionValue(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


class Stage(StrEnum):
    INPUT_CHECK = "input_check"
    PREPROCESS = "preprocess"
    KB_RETRIEVE = "kb_retrieve"
    BLIND_REVIEW = "blind_review"
    FUSION = "fusion"
    VOTE = "vote"
    ARBITRATION = "arbitration"
    VERDICT = "verdict"
    RENDER = "render"


STAGE_ORDER: tuple[Stage, ...] = (
    Stage.INPUT_CHECK,
    Stage.PREPROCESS,
    Stage.KB_RETRIEVE,
    Stage.BLIND_REVIEW,
    Stage.FUSION,
    Stage.VOTE,
    Stage.ARBITRATION,
    Stage.VERDICT,
    Stage.RENDER,
)

ALWAYS_REQUIRED_STAGES: frozenset[Stage] = frozenset(
    {
        Stage.INPUT_CHECK,
        Stage.BLIND_REVIEW,
        Stage.FUSION,
        Stage.VOTE,
        Stage.VERDICT,
        Stage.RENDER,
    }
)


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class DegradedReason(StrEnum):
    KB_MODULE_MISSING = "kb_module_missing"
    RAW_TEXT_UNPARSED = "raw_text_unparsed"
    VECTOR_UNAVAILABLE = "vector_unavailable"
    KEYWORD_UNAVAILABLE = "keyword_unavailable"
    RERANK_SKIPPED = "rerank_skipped"
    MODEL_MISSING = "model_missing"
    SCOPE_MISSING = "scope_missing"
    AUTOMATION_CONTEXT_MISSING = "automation_context_missing"
    BUDGET_EXCEEDED = "budget_exceeded"
    ARBITRATION_SKIPPED = "arbitration_skipped"


class CandidateStatus(StrEnum):
    CANDIDATE = "candidate"
    DISPUTED = "disputed"
    MERGED = "merged"


class VoteValidity(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    UNCERTAIN = "uncertain"
    NOT_ASSESSED = "not_assessed"


class Severity(StrEnum):
    BLOCKER = "blocker"
    MAJOR = "major"
    SUGGESTION = "suggestion"


SEVERITY_RANK: dict[str, int] = {"suggestion": 0, "major": 1, "blocker": 2}
SEVERITY_BY_RANK: dict[int, str] = {rank: name for name, rank in SEVERITY_RANK.items()}


class IssueStatus(StrEnum):
    ADOPTED = "adopted"
    REJECTED = "rejected"
    DISPUTED = "disputed"
    NEED_HUMAN = "need_human"
    CHIEF_SUPPLEMENT = "chief_supplement"


class ChiefDecision(StrEnum):
    ADOPT = "adopt"
    REJECT = "reject"
    DISPUTE = "dispute"
    NEED_HUMAN = "need_human"
    SUPPLEMENT = "supplement"


class VoteCompleteness(StrEnum):
    FULL = "3/3"
    PARTIAL = "2/3"
    ONE = "1/3"
    NONE = "0/3"


class EvidenceType(StrEnum):
    BUSINESS_RULE = "business_rule"
    REQUIREMENT = "requirement"
    KNOWN_LIMIT = "known_limit"
    HISTORICAL_BUG = "historical_bug"
    TESTING_STANDARD = "testing_standard"
    INFERENCE = "inference"


class EvidenceLevel(StrEnum):
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"


class EvidenceStrength(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"


class EvidenceStatus(StrEnum):
    GROUNDED = "grounded"
    PARTIALLY_GROUNDED = "partially_grounded"
    UNGROUNDED = "ungrounded"
    CONFLICTED = "conflicted"
    INSUFFICIENT = "insufficient"


class ClaimStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    CONFLICTED = "conflicted"
    INSUFFICIENT = "insufficient"


class ClaimRole(StrEnum):
    CORE = "core"
    SUPPORTING = "supporting"


class ClaimRelation(StrEnum):
    AND = "and"
    OR = "or"


class Dimension(StrEnum):
    """报告 issue 维度（schemas/report.schema.json `issue.dimension`）。"""

    BUSINESS = "business"
    TEST_DESIGN = "test_design"
    AUTOMATION = "automation"


class ValidationStatus(StrEnum):
    PASSED = "passed"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class DecisionStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class ConfidenceSource(StrEnum):
    UNCALIBRATED = "uncalibrated"
    CALIBRATED = "calibrated"


class DocType(StrEnum):
    REQUIREMENT = "requirement"
    RULE = "rule"
    DESIGN = "design"
    GM_COMMAND = "gm_command"
    KNOWN_LIMIT = "known_limit"
    HISTORY_BUG = "history_bug"
    TERM = "term"
    FLOW = "flow"


class RuleStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class KbVersionStatus(StrEnum):
    BUILDING = "building"
    CANDIDATE = "candidate"
    ACTIVE = "active"
    RETIRED = "retired"
    FAILED = "failed"


class OriginType(StrEnum):
    REQUIREMENT = "requirement"
    SPECIFICATION = "specification"
    TEST_STANDARD = "test_standard"
    HISTORICAL_BUG = "historical_bug"
    EXPERT_RULE = "expert_rule"


class Role(StrEnum):
    REVIEWER = "reviewer"
    APPROVER = "approver"
    ADMIN = "admin"
    KB_CREATOR = "kb_creator"
    KB_REVIEWER = "kb_reviewer"
    KB_PUBLISHER = "kb_publisher"


class ActorType(StrEnum):
    SERVICE = "service"
    HUMAN = "human"


class Topology(StrEnum):
    SINGLE = "single"
    DUAL = "dual"
    MULTI = "multi"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    TESTING = "testing"
    VERIFIED = "verified"
    DEPRECATED = "deprecated"


class ParticipantStatus(StrEnum):
    ACTIVE = "active"
    FAILED = "failed"
    ABSENT = "absent"


class ReviewTaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReviewLevel(StrEnum):
    ISSUE = "issue"
    REPORT = "report"


class IssueTaskResult(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    MODIFIED = "modified"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    ESCALATED = "escalated"


class GapType(StrEnum):
    KNOWLEDGE_MISSING = "knowledge_missing"
    RETRIEVAL_MISSED = "retrieval_missed"
    KNOWLEDGE_CONFLICT = "knowledge_conflict"
    KNOWLEDGE_OUTDATED = "knowledge_outdated"


class GapResolution(StrEnum):
    ADD_KNOWLEDGE = "add_knowledge"
    UPDATE_KNOWLEDGE = "update_knowledge"
    ADJUST_RETRIEVAL = "adjust_retrieval"
    FIX_APPLICABILITY = "fix_applicability"
    RESOLVE_CONFLICT = "resolve_conflict"
    NO_ACTION = "no_action"


class GapStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    MERGED = "merged"


class ReviewParticipantRole(StrEnum):
    """评审席位角色（docs/17 §5.1、docs/12 §2）。"""

    CHIEF_BLIND = "chief_blind"
    JURY_A = "jury_a"
    JURY_B = "jury_b"


class ModelRunStatus(StrEnum):
    OK = "ok"
    TIMEOUT = "timeout"
    ERROR = "error"
    PARSE_ERROR = "parse_error"
