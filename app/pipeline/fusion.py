"""问题融合（M0 规则分桶版；向量/rerank 在 M3 接入）。

M0 只做规则键分桶：`(step_index ± STEP_TOLERANCE, category)`；
同一桶合并为一条候选，保留 `merged_from` 与 `proposed_by`。
候选的标准化描述只描述现象，不带严重级倾向（防投票锚定，docs/12 §7）。
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any
from uuid import uuid4

from app.core.enums import SEVERITY_RANK
from app.llm.base import ReviewOpinion
from app.pipeline.verdict import Claim, aggregate_claim_evidence
from app.storage.models import CandidateRecord

SEVERITY_BY_RANK = {0: "suggestion", 1: "major", 2: "blocker"}


def _canonical_claims(issue: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for item in issue.get("claims") or []:
        claims.append(
            {
                "claim_id": item.get("claim_id", "claim_001"),
                "claim_role": item.get("claim_role", "core"),
                "relation": item.get("relation", "and"),
                "claim_text": item.get("claim_text", issue.get("rationale", "")),
                "evidence_level": item.get("evidence_level", "E4"),
                "evidence_status": item.get("evidence_status", "unsupported"),
                "evidence_refs": item.get("evidence_refs", []),
            }
        )
    return claims


def _aggregate_status(claims: list[dict[str, Any]]) -> str:
    parsed = [
        Claim(
            role=str(item.get("claim_role")),
            status=str(item.get("evidence_status")),
            level=str(item.get("evidence_level")),
        )
        for item in claims
    ]
    return aggregate_claim_evidence(parsed)


def _issue_evidence_status(issue: dict[str, Any]) -> str:
    """模型直接给出问题级 evidence_status 时使用（无 claim 结构）。"""

    value = str(issue.get("evidence_status") or "ungrounded")
    allowed = {"grounded", "partially_grounded", "ungrounded", "conflicted", "insufficient"}
    return value if value in allowed else "ungrounded"


def _standardize(
    step_index: int | None, category: str, rationale: str | None
) -> str:
    """投票材料：只描述现象与事实，去掉严重级倾向，避免锚定（docs/12 §7）。"""

    location = f"第 {step_index} 步" if step_index is not None else "用例整体"
    detail = (rationale or "").strip()
    detail = re.sub(r"(blocker|major|suggestion|阻断|严重|致命)", "", detail, flags=re.IGNORECASE)
    detail = re.sub(r"\s+", " ", detail).strip(" ：:。")
    if detail:
        text = f"{location}存在「{category}」问题：{detail}"
    else:
        text = f"{location}存在「{category}」问题"
    return text[:300]


def fuse(
    review_id: str,
    case: dict[str, Any],
    opinions: list[ReviewOpinion],
    *,
    step_tolerance: int = 1,
) -> list[CandidateRecord]:
    buckets: dict[tuple[int | None, str], list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for opinion in opinions:
        for issue in opinion.issues:
            buckets[(issue.get("step_index"), str(issue.get("category")))].append(
                (opinion.role, issue)
            )

    ordered = sorted(
        buckets.items(),
        key=lambda item: (
            item[0][0] is None,
            item[0][0] if item[0][0] is not None else 0,
            item[0][1],
        ),
    )

    candidates: list[CandidateRecord] = []
    for candidate_no, ((step_index, category), members) in enumerate(ordered, start=1):
        strongest = max(
            members,
            key=lambda item: SEVERITY_RANK.get(str(item[1].get("severity")), 0),
        )
        claims = _canonical_claims(strongest[1])
        severity_proposal = SEVERITY_BY_RANK[
            max(SEVERITY_RANK.get(str(issue.get("severity")), 0) for _, issue in members)
        ]
        evidence_status = (
            _aggregate_status(claims) if claims else _issue_evidence_status(strongest[1])
        )
        candidates.append(
            CandidateRecord(
                id=str(uuid4()),
                review_id=review_id,
                candidate_no=candidate_no,
                step_index=step_index,
                dimension=str(strongest[1].get("dimension", "test_design")),
                standardized_text=_standardize(
                    step_index, category, strongest[1].get("rationale")
                ),
                severity_proposal=severity_proposal,
                claims=claims,
                evidence_status=evidence_status,
                evidence_refs=[],
                kb_grounded=bool(strongest[1].get("kb_grounded", False)),
                kb_refs=list(strongest[1].get("kb_refs") or []),
                evidence_type=strongest[1].get("evidence_type"),
                evidence_strength=strongest[1].get("evidence_strength"),
                evidence_quote=strongest[1].get("evidence_quote"),
                model_evidence_status=strongest[1].get("model_evidence_status"),
                evidence_support_status=strongest[1].get("evidence_support_status"),
                validation_status=str(strongest[1].get("validation_status") or "passed"),
                parse_warnings=list(strongest[1].get("parse_warnings") or []),
                model_confidence=strongest[1].get("model_confidence"),
                suggestion=strongest[1].get("suggestion"),
                proposed_by=sorted({role for role, _ in members}),
                merged_from=[
                    {
                        "reviewer": role,
                        "text": issue.get("rationale"),
                        "step_index": issue.get("step_index"),
                        "severity": issue.get("severity"),
                    }
                    for role, issue in members
                ],
                fusion_basis={
                    "bucket": f"step={step_index},category={category}",
                    "tolerance": step_tolerance,
                    "rule": "same_step_and_category",
                },
                category=category,
            )
        )
    return candidates
