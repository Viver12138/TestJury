"""ACC-CON-010：docs/12 §8 禁止组合在实现层必须可被检出，且正常路径永不产生。"""

from __future__ import annotations

import random

from app.pipeline.verdict import (
    IssueTrace,
    VerdictResult,
    check_forbidden,
    compute_verdict,
)


def _result(
    ai_verdict: str | None,
    traces: list[IssueTrace],
) -> VerdictResult:
    return VerdictResult(
        ai_verdict=ai_verdict,
        issue_statuses={trace.candidate_id: trace.status for trace in traces},
        human_review_required=False,
        review_completeness="full",
        arbitration_required=False,
        traces=traces,
    )


def test_approved_is_always_forbidden() -> None:
    violations = check_forbidden(_result("approved", []), participants=3)
    assert any("approved" in item for item in violations)


def test_blocked_without_blocker_is_forbidden() -> None:
    trace = IssueTrace(
        candidate_id="C1", evidence_status="grounded", status="major", severity="major"
    )
    violations = check_forbidden(_result("blocked", [trace]), participants=3)
    assert any("blocked 但无 blocker" in item for item in violations)


def test_conditional_with_disputed_is_forbidden() -> None:
    trace = IssueTrace(candidate_id="C1", evidence_status="grounded", status="disputed")
    violations = check_forbidden(_result("conditional", [trace]), participants=3)
    assert any("conditional" in item for item in violations)


def test_single_participant_cannot_have_formal_verdict() -> None:
    violations = check_forbidden(_result("conditional", []), participants=1)
    assert any("1 席位" in item for item in violations)


def test_two_or_three_participants_must_have_verdict() -> None:
    empty = _result(None, [])
    assert check_forbidden(empty, participants=2) != []
    assert check_forbidden(empty, participants=3) != []


def test_blocker_with_ungrounded_evidence_is_forbidden() -> None:
    trace = IssueTrace(
        candidate_id="C1",
        evidence_status="ungrounded",
        status="blocker",
        severity="blocker",
    )
    violations = check_forbidden(_result("blocked", [trace]), participants=3)
    assert any("ungrounded" in item for item in violations)


def test_random_inputs_never_violate_forbidden_combinations() -> None:
    rng = random.Random(2026)
    for _ in range(500):
        participants = rng.choice([0, 1, 2, 3])
        issues = []
        for index in range(rng.randint(0, 2)):
            votes = []
            for _seat in range(participants):
                validity = rng.choice(["accept", "reject", "uncertain", "not_assessed"])
                severity = rng.choice(["blocker", "major", "suggestion"]) if validity == "accept" else None
                votes.append([validity, severity])
            issues.append(
                {
                    "candidate_id": f"C{index + 1}",
                    "votes": votes,
                    "evidence_status": rng.choice(
                        ["grounded", "partially_grounded", "ungrounded", "conflicted", "insufficient"]
                    ),
                }
            )
        payload = {"participants": participants, "issues": issues}
        result = compute_verdict(payload)
        assert check_forbidden(result, participants) == []
        assert result.ai_verdict != "approved"
