"""Verdict 唯一计算入口（docs/12、docs/06 §3.1）。

约束：
- `ai_verdict` 只能由本模块产生；模型/仲裁输出只作输入，不直接写结论。
- 纯函数，不读数据库、不调模型；与 `scripts/verdict_reference.py` 对同一批用例必须一致。
- 顺序固定、命中即停（docs/12 §4）；`approved` 永不出现。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.core.enums import (
    SEVERITY_BY_RANK,
    SEVERITY_RANK,
    ClaimRole,
    ClaimStatus,
    EvidenceLevel,
    EvidenceStatus,
    IssueStatus,
    Severity,
    VoteValidity,
)

VALIDITY_STATES = {item.value for item in VoteValidity}
SEVERITY_STATES = {item.value for item in Severity}
EVIDENCE_STATES = {item.value for item in EvidenceStatus}
CLAIM_STATES = {item.value for item in ClaimStatus}
CLAIM_ROLES = {item.value for item in ClaimRole}
CLAIM_LEVELS = {item.value for item in EvidenceLevel}


class VerdictInputError(ValueError):
    """输入违反 docs/12 的字段约束（数据非法，不是业务结论）。"""


@dataclass(frozen=True)
class Vote:
    validity: str
    severity: str | None = None


@dataclass(frozen=True)
class Claim:
    role: str
    status: str
    level: str


@dataclass
class IssueInput:
    candidate_id: str
    votes: list[Vote]
    claims: list[Claim] | None = None
    evidence_status: str | None = None


@dataclass
class VerdictInput:
    participants: int
    issues: list[IssueInput] = field(default_factory=list)


@dataclass
class IssueTrace:
    """单条候选的判定轨迹。

    `status` 与参考判定器（scripts/verdict_reference.py）保持一致：
    `blocker` / `major` / `suggestion` / `rejected` / `disputed` / `need_human`。
    报告字段 `issues.status`（docs/17）用 `issue_status` 映射，两者不混用。
    """

    candidate_id: str
    evidence_status: str
    validity: str | None = None
    severity: str | None = None
    severity_provisional: bool = False
    status: str = IssueStatus.NEED_HUMAN.value
    triggers: list[str] = field(default_factory=list)

    @property
    def issue_status(self) -> str:
        if self.status in (Severity.BLOCKER.value, Severity.MAJOR.value, Severity.SUGGESTION.value):
            return IssueStatus.ADOPTED.value
        if self.status == IssueStatus.REJECTED.value:
            return IssueStatus.REJECTED.value
        if self.status == IssueStatus.DISPUTED.value:
            return IssueStatus.DISPUTED.value
        return IssueStatus.NEED_HUMAN.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "evidence_status": self.evidence_status,
            "validity": self.validity,
            "severity": self.severity,
            "severity_provisional": self.severity_provisional,
            "status": self.status,
            "issue_status": self.issue_status,
            "triggers": list(self.triggers),
        }


@dataclass
class VerdictResult:
    ai_verdict: str | None
    issue_statuses: dict[str, str]
    human_review_required: bool
    review_completeness: str
    arbitration_required: bool
    traces: list[IssueTrace]

    @property
    def report_issue_statuses(self) -> dict[str, str]:
        """报告投影使用的 `issues.status`（docs/17 枚举）。"""

        return {trace.candidate_id: trace.issue_status for trace in self.traces}

    def to_dict(self) -> dict[str, Any]:
        return {
            "ai_verdict": self.ai_verdict,
            "issue_statuses": dict(self.issue_statuses),
            "report_issue_statuses": self.report_issue_statuses,
            "human_review_required": self.human_review_required,
            "review_completeness": self.review_completeness,
            "arbitration_required": self.arbitration_required,
            "traces": [trace.to_dict() for trace in self.traces],
        }


# ───────────────────────── 输入规范化 ─────────────────────────


def _coerce_votes(raw: Any, participants: int, label: str) -> list[Vote]:
    if isinstance(raw, Mapping):
        items: Iterable[Any] = list(raw.values())
    elif isinstance(raw, list):
        items = raw
    else:
        raise VerdictInputError(f"{label}.votes 必须是数组或对象")

    votes: list[Vote] = []
    for index, item in enumerate(items):
        if isinstance(item, Vote):
            vote = item
        elif isinstance(item, Mapping):
            validity = item.get("validity")
            severity = item.get("severity")
            vote = Vote(validity=validity, severity=severity)  # type: ignore[arg-type]
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            vote = Vote(validity=item[0], severity=item[1])
        else:
            raise VerdictInputError(f"{label}.votes[{index}] 必须是 [validity, severity] 或对象")

        if vote.validity not in VALIDITY_STATES:
            raise VerdictInputError(f"{label}.votes[{index}].validity 非法: {vote.validity!r}")
        if vote.severity is not None:
            if vote.severity not in SEVERITY_STATES:
                raise VerdictInputError(f"{label}.votes[{index}].severity 非法: {vote.severity!r}")
            if vote.validity != VoteValidity.ACCEPT.value:
                raise VerdictInputError(
                    f"{label}.votes[{index}] validity={vote.validity} 时不得携带 severity"
                )
        votes.append(vote)

    if len(votes) != participants:
        raise VerdictInputError(
            f"{label}.votes 数量 {len(votes)} 与 participants {participants} 不一致"
        )
    return votes


def _coerce_claims(raw: Any, label: str) -> list[Claim] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise VerdictInputError(f"{label}.claims 必须是非空数组")
    claims: list[Claim] = []
    for index, item in enumerate(raw):
        if isinstance(item, Claim):
            claim = item
        elif isinstance(item, Mapping):
            claim = Claim(
                role=item.get("role") or item.get("claim_role"),  # type: ignore[arg-type]
                status=item.get("status") or item.get("evidence_status"),  # type: ignore[arg-type]
                level=item.get("level") or item.get("evidence_level"),  # type: ignore[arg-type]
            )
        else:
            raise VerdictInputError(f"{label}.claims[{index}] 必须是对象")
        if claim.role not in CLAIM_ROLES:
            raise VerdictInputError(f"{label}.claims[{index}].role 非法: {claim.role!r}")
        if claim.status not in CLAIM_STATES:
            raise VerdictInputError(f"{label}.claims[{index}].status 非法: {claim.status!r}")
        if claim.level not in CLAIM_LEVELS:
            raise VerdictInputError(f"{label}.claims[{index}].level 非法: {claim.level!r}")
        claims.append(claim)
    cores = [claim for claim in claims if claim.role == ClaimRole.CORE.value]
    if len(cores) != 1:
        raise VerdictInputError(f"{label}.claims 必须且只能有 1 个 core，实际 {len(cores)}")
    return claims


def normalize_input(payload: VerdictInput | Mapping[str, Any]) -> VerdictInput:
    if isinstance(payload, VerdictInput):
        participants = payload.participants
        if participants not in (0, 1, 2, 3):
            raise VerdictInputError(f"participants 必须是 0..3，实际 {participants!r}")
        issues = [
            IssueInput(
                candidate_id=issue.candidate_id,
                votes=_coerce_votes(issue.votes, participants, issue.candidate_id),
                claims=_coerce_claims(issue.claims, issue.candidate_id),
                evidence_status=issue.evidence_status,
            )
            for issue in payload.issues
        ]
        return VerdictInput(participants=participants, issues=issues)
    participants = payload.get("participants")
    if participants not in (0, 1, 2, 3):
        raise VerdictInputError(f"participants 必须是 0..3，实际 {participants!r}")
    raw_issues = payload.get("issues", [])
    if not isinstance(raw_issues, list):
        raise VerdictInputError("issues 必须是数组")
    issues = [
        IssueInput(
            candidate_id=str(issue.get("candidate_id")),
            votes=_coerce_votes(issue.get("votes", []), participants, str(issue.get("candidate_id"))),
            claims=_coerce_claims(issue.get("claims"), str(issue.get("candidate_id"))),
            evidence_status=issue.get("evidence_status"),
        )
        for issue in raw_issues
    ]
    return VerdictInput(participants=participants, issues=issues)


# ───────────────────────── claim 聚合 ─────────────────────────


def aggregate_claim_evidence(claims: list[Claim]) -> str:
    """按 docs/12 §4.1 聚合问题级 evidence_status（固定算法，命中即停）。"""

    statuses = [claim.status for claim in claims]
    if ClaimStatus.CONFLICTED.value in statuses:
        return EvidenceStatus.CONFLICTED.value
    levels = [claim.level for claim in claims]
    if not any(level in (EvidenceLevel.E1.value, EvidenceLevel.E2.value) for level in levels):
        return EvidenceStatus.UNGROUNDED.value
    core = next(claim for claim in claims if claim.role == ClaimRole.CORE.value)
    if core.status in (ClaimStatus.UNSUPPORTED.value, ClaimStatus.INSUFFICIENT.value):
        return EvidenceStatus.INSUFFICIENT.value
    if any(claim.status != ClaimStatus.SUPPORTED.value for claim in claims):
        return EvidenceStatus.PARTIALLY_GROUNDED.value
    if core.level not in (EvidenceLevel.E1.value, EvidenceLevel.E2.value):
        return EvidenceStatus.UNGROUNDED.value
    return EvidenceStatus.GROUNDED.value


# ───────────────────────── 逐条判定 ─────────────────────────


def _validity_decision(votes: list[Vote]) -> str:
    effective = [vote for vote in votes if vote.validity != VoteValidity.NOT_ASSESSED.value]
    if len(effective) < 2:
        return "need_human"
    accept = sum(1 for vote in effective if vote.validity == VoteValidity.ACCEPT.value)
    reject = sum(1 for vote in effective if vote.validity == VoteValidity.REJECT.value)
    if accept >= 2 and reject < 2:
        return "accepted"
    if reject >= 2:
        return "rejected"
    if len(effective) == 2 and accept == 1 and reject == 0:
        return "insufficient"
    if len(effective) == 2 and accept == 0 and reject == 1:
        return "insufficient"
    return "disputed"


def _severity_decision(votes: list[Vote]) -> tuple[str, str | None, bool]:
    accepted = [vote for vote in votes if vote.validity == VoteValidity.ACCEPT.value]
    present = [vote.severity for vote in accepted if vote.severity is not None]
    if not present:
        return "missing", None, False
    ranks = [SEVERITY_RANK[severity] for severity in present]
    if max(ranks) - min(ranks) >= 2:
        return "severity_disputed", None, False
    severity = SEVERITY_BY_RANK[max(ranks)]
    provisional = (max(ranks) - min(ranks) == 1) or len(present) < len(accepted)
    if severity == Severity.BLOCKER.value and len(present) < len(accepted):
        # blocker 不能建立在"accept 但没给严重级"的票上
        return "missing", None, provisional
    return "ok", severity, provisional


def _issue_status(issue: IssueInput, participants: int) -> IssueTrace:
    votes = issue.votes
    claims = issue.claims

    if claims is not None:
        evidence_status = aggregate_claim_evidence(claims)
    else:
        evidence_status = issue.evidence_status or EvidenceStatus.UNGROUNDED.value
        if evidence_status not in EVIDENCE_STATES:
            raise VerdictInputError(
                f"{issue.candidate_id}.evidence_status 非法: {evidence_status!r}"
            )

    trace = IssueTrace(candidate_id=issue.candidate_id, evidence_status=evidence_status)

    if participants < 2:
        trace.triggers.append("insufficient_participants")
        return trace
    effective = [vote for vote in votes if vote.validity != VoteValidity.NOT_ASSESSED.value]
    if len(effective) < 2:
        trace.triggers.append("insufficient_votes")
        return trace

    if evidence_status == EvidenceStatus.CONFLICTED.value:
        trace.triggers.append("evidence_conflict")
        return trace

    validity = _validity_decision(votes)
    trace.validity = validity

    if validity == "rejected":
        trace.status = IssueStatus.REJECTED.value
        return trace
    if validity == "disputed":
        trace.status = IssueStatus.DISPUTED.value
        trace.triggers.append("validity_disputed")
        return trace
    if validity == "insufficient":
        trace.triggers.append("validity_insufficient")
        return trace

    severity_state, severity, provisional = _severity_decision(votes)
    trace.severity = severity
    trace.severity_provisional = provisional
    if severity_state == "severity_disputed":
        trace.triggers.append("severity_disputed")
        return trace
    if severity_state == "missing":
        trace.triggers.append("severity_missing")
        return trace

    assert severity is not None
    if severity == Severity.BLOCKER.value:
        if evidence_status not in (
            EvidenceStatus.GROUNDED.value,
            EvidenceStatus.PARTIALLY_GROUNDED.value,
        ):
            trace.triggers.append("blocker_without_evidence")
            return trace
        if claims is not None:
            core = next(claim for claim in claims if claim.role == ClaimRole.CORE.value)
            if core.status != ClaimStatus.SUPPORTED.value or core.level not in (
                EvidenceLevel.E1.value,
                EvidenceLevel.E2.value,
            ):
                trace.triggers.append("blocker_core_claim_unsupported")
                return trace
        trace.status = Severity.BLOCKER.value
        if evidence_status == EvidenceStatus.PARTIALLY_GROUNDED.value:
            trace.triggers.append("partially_grounded_blocker")
        if participants < 3:
            trace.triggers.append("blocker_in_partial_review")
        return trace

    trace.status = severity
    return trace


# ───────────────────────── 报告级 ─────────────────────────


def compute_verdict(payload: VerdictInput | Mapping[str, Any]) -> VerdictResult:
    normalized = normalize_input(payload)
    participants = normalized.participants
    seen: set[str] = set()
    traces: list[IssueTrace] = []
    for issue in normalized.issues:
        if not issue.candidate_id:
            raise VerdictInputError("issue.candidate_id 必须是非空字符串")
        if issue.candidate_id in seen:
            raise VerdictInputError(f"candidate_id 重复: {issue.candidate_id}")
        seen.add(issue.candidate_id)
        traces.append(_issue_status(issue, participants))

    statuses = {trace.candidate_id: trace.status for trace in traces}
    status_values = list(statuses.values())

    if participants == 0:
        ai_verdict: str | None = None
        completeness = "failed"
    elif participants == 1:
        ai_verdict = None
        completeness = "insufficient"
    else:
        completeness = "full" if participants == 3 else "partial"
        if Severity.BLOCKER.value in status_values:
            ai_verdict = "blocked"
        elif any(
            status in (IssueStatus.DISPUTED.value, IssueStatus.NEED_HUMAN.value)
            for status in status_values
        ):
            ai_verdict = "need_human"
        else:
            ai_verdict = "conditional"

    human_review_required = any(
        trace.status in (IssueStatus.DISPUTED.value, IssueStatus.NEED_HUMAN.value)
        or "partially_grounded_blocker" in trace.triggers
        or "blocker_in_partial_review" in trace.triggers
        for trace in traces
    )
    arbitration_required = any(
        "validity_disputed" in trace.triggers
        or "severity_disputed" in trace.triggers
        or "evidence_conflict" in trace.triggers
        for trace in traces
    )

    return VerdictResult(
        ai_verdict=ai_verdict,
        issue_statuses=statuses,
        human_review_required=human_review_required,
        review_completeness=completeness,
        arbitration_required=arbitration_required,
        traces=traces,
    )


def check_forbidden(result: VerdictResult, participants: int) -> list[str]:
    """检查 docs/12 §8 禁止组合；返回违规描述（空 = 合法）。"""

    violations: list[str] = []
    statuses = list(result.issue_statuses.values())

    if result.ai_verdict == "approved":
        violations.append("ai_verdict 不得为 approved")
    if result.ai_verdict == "blocked" and Severity.BLOCKER.value not in statuses:
        violations.append("blocked 但无 blocker 问题")
    if result.ai_verdict == "conditional" and any(
        status in (IssueStatus.DISPUTED.value, IssueStatus.NEED_HUMAN.value) for status in statuses
    ):
        violations.append("conditional 但存在 disputed/need_human")
    if participants in (0, 1) and result.ai_verdict is not None:
        violations.append(f"{participants} 席位参与时不得给出正式 ai_verdict")
    if participants in (2, 3) and result.ai_verdict is None:
        violations.append(f"{participants} 席位参与时不得为空 ai_verdict")
    if any(
        trace.status == Severity.BLOCKER.value
        and trace.evidence_status == EvidenceStatus.UNGROUNDED.value
        for trace in result.traces
    ):
        violations.append("blocker 且 evidence_status=ungrounded")
    return violations
