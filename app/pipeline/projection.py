"""报告投影：`report_json.issues` → `issues` 表（只读派生，docs/02 §3.22、docs/14 §7）。

- 投影只用于查询/统计，不是事实源；重建必须从 `report_json` 重新生成。
- `issue id` 用 `uuid5(review_id + issue_no)` 生成，保证重建幂等。
- 一致性检查覆盖数量、编号、严重级、状态、维度、分类与理由，避免"投影看起来有、实际已漂移"。
"""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.storage.models import IssueRecord

PROJECTION_FIELDS = (
    "issue_no",
    "candidate_id",
    "step_index",
    "dimension",
    "severity",
    "category",
    "rationale",
    "suggestion",
    "status",
    "evidence_status",
    "evidence_type",
    "evidence_strength",
    "kb_grounded",
    "proposed_by",
    "chief_decision",
    "chief_reason",
    "human_verdict",
)


def issue_id_for(review_id: str, issue_no: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"testjury:{review_id}:{issue_no}"))


def records_from_report(review_id: str, report: dict[str, Any]) -> list[IssueRecord]:
    records: list[IssueRecord] = []
    for issue in report.get("issues") or []:
        issue_no = int(issue["issue_no"])
        records.append(
            IssueRecord(
                id=issue_id_for(review_id, issue_no),
                review_id=review_id,
                issue_no=issue_no,
                candidate_id=issue.get("candidate_id"),
                step_index=issue.get("step_index"),
                dimension=str(issue["dimension"]),
                severity=str(issue["severity"]),
                category=str(issue["category"]),
                evidence_quote=issue.get("evidence_quote"),
                rationale=str(issue["rationale"]),
                suggestion=issue.get("suggestion"),
                status=str(issue["status"]),
                evidence_status=issue.get("evidence_status"),
                evidence_type=issue.get("evidence_type"),
                evidence_strength=issue.get("evidence_strength"),
                kb_grounded=bool(issue.get("kb_grounded", False)),
                kb_refs=list(issue.get("kb_refs") or []),
                evidence_refs=list(issue.get("evidence_refs") or []),
                proposed_by=list(issue.get("proposed_by") or []),
                confidence=issue.get("confidence"),
                confidence_source=str(issue.get("confidence_source") or "uncalibrated"),
                model_confidence=issue.get("model_confidence"),
                validation_status=issue.get("validation_status"),
                evidence_support_status=issue.get("evidence_support_status"),
                decision_status=issue.get("decision_status"),
                chief_decision=issue.get("chief_decision"),
                chief_reason=issue.get("chief_reason"),
                human_verdict=issue.get("human_verdict"),
            )
        )
    return records


def record_to_dict(record: IssueRecord) -> dict[str, Any]:
    return {field: getattr(record, field) for field in PROJECTION_FIELDS}


def compare_projection(review_id: str, report: dict[str, Any], records: list[IssueRecord]) -> list[str]:
    """返回差异描述（空 = 一致）。"""

    expected = {record.issue_no: record for record in records_from_report(review_id, report)}
    actual = {record.issue_no: record for record in records}
    problems: list[str] = []
    if len(expected) != len(actual):
        problems.append(f"issue 数量不一致: report={len(expected)} projection={len(actual)}")
    for issue_no in sorted(set(expected) | set(actual)):
        if issue_no not in actual:
            problems.append(f"ISSUE-{issue_no:03d} 缺少投影")
            continue
        if issue_no not in expected:
            problems.append(f"ISSUE-{issue_no:03d} 投影多余")
            continue
        want = expected[issue_no]
        got = actual[issue_no]
        for field in PROJECTION_FIELDS:
            want_value = getattr(want, field)
            got_value = getattr(got, field)
            if field in ("kb_grounded",):
                want_value, got_value = bool(want_value), bool(got_value)
            if want_value != got_value:
                problems.append(
                    f"ISSUE-{issue_no:03d}.{field} 不一致: report={want_value!r} projection={got_value!r}"
                )
    return problems
