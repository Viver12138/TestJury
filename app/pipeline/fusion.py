"""按问题位置、原文、知识来源和修正断言保守合并候选。

同一步骤与分类只是搜索范围；不同修正值或不同对象保持独立。
合并后保留 `merged_from` 与 `proposed_by`。
候选的标准化描述只描述现象，不带严重级倾向（防投票锚定，docs/12 §7）。
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.core.enums import SEVERITY_RANK
from app.knowledge.runtime import tokens
from app.llm.base import ReviewOpinion
from app.pipeline.verdict import Claim, aggregate_claim_evidence
from app.storage.models import CandidateRecord

SEVERITY_BY_RANK = {0: "suggestion", 1: "major", 2: "blocker"}


def _correction_assertions(text: str) -> set[tuple[str, str]]:
    # Selectors identify an object; their arguments are not corrected values.
    selectors = [m.span() for m in re.finditer(r"[a-zA-Z_][a-zA-Z0-9_.]*\([^()\n]*\)", text)]
    pattern = (r"(?<![a-zA-Z0-9_.])([a-zA-Z_][a-zA-Z0-9_.]*(?:\([^()\n]*\))?(?:\.[a-zA-Z0-9_]+)*)\s*"
               r"(?:=|应为|改为|仍为|保持(?:为)?)\s*"
               r"(-?\d+(?:\.\d+)?|[A-Z][A-Z0-9_]*|null|None|true|false)(?![a-zA-Z0-9_.])")
    result = set()
    for match in re.finditer(pattern, text):
        if any(start < match.start() < end for start, end in selectors):
            continue
        field, value = match.groups()
        field = re.sub(r"\s+", "", field)
        value = str(Decimal(value).normalize()) if re.fullmatch(r"-?\d+(?:\.\d+)?", value) else value
        result.add((field, value))
    return result


def _http_error_signature(text: str) -> tuple[set[str], set[str]]:
    codes = set(re.findall(r"(?<![a-zA-Z0-9_])HTTP\s*([45]\d{2})(?!\d)", text, re.IGNORECASE))
    messages = re.findall(r'[“「"]([^”」"\n]{4,120})[”」"]', text)
    messages += re.findall(r'(?:错误信息|message)\s*(?:为|是|=|[:：])\s*([^；;，,。\n]+)', text)
    normalized = {re.sub(r"\s+", "", m.strip('“”「」" ')) for m in messages}
    return codes, normalized


def _same_http_error(left: str, right: str) -> bool:
    left_codes, left_messages = _http_error_signature(left)
    right_codes, right_messages = _http_error_signature(right)
    return (len(left_codes) == 1 and left_codes == right_codes
            and bool(left_messages) and left_messages == right_messages)


def _conflicting_http_errors(left: str, right: str) -> bool:
    left_codes, left_messages = _http_error_signature(left)
    right_codes, right_messages = _http_error_signature(right)
    return bool(left_codes and right_codes and (
        left_codes != right_codes or (left_messages and right_messages and left_messages != right_messages)))


def _different_selected_objects(left: str, right: str) -> bool:
    return (left != right and '(' in left + right
            and re.sub(r'\([^()]*\)', '', left) == re.sub(r'\([^()]*\)', '', right))



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

    # Same category/step is a search bucket, not proof of the same root cause.
    clusters = []
    for key, members in ordered:
        groups: list[list[tuple[str, dict[str, Any]]]] = []
        for member in members:
            issue = member[1]
            found = None
            for group in groups:
                other = group[0][1]
                left, right = set(tokens(str(issue.get("rationale")))), set(tokens(str(other.get("rationale"))))
                overlap = len(left & right) / max(1, len(left | right))
                containment = len(left & right) / max(1, min(len(left), len(right)))
                corrections = _correction_assertions(str(issue.get("suggestion") or ""))
                other_corrections = _correction_assertions(str(other.get("suggestion") or ""))
                original = _correction_assertions(str(issue.get("evidence_quote") or ""))
                other_original = _correction_assertions(str(other.get("evidence_quote") or ""))
                # Suggestions may echo the old invalid value ("...is ignored") and
                # add unrelated observations. Compare changed assertions about the
                # quoted fields, without treating an echoed old value as a new fix.
                changed = {(field, value) for field, value in corrections - original
                           if field in {f for f, _ in original}}
                other_changed = {(field, value) for field, value in other_corrections - other_original
                                 if field in {f for f, _ in other_original}}
                if changed and other_changed:
                    corrections, other_corrections = changed, other_changed
                same_correction = bool(corrections & other_corrections)
                identical_corrections = bool(corrections) and (
                    corrections == other_corrections or (len(corrections & other_corrections) >= 2
                        and (corrections <= other_corrections or other_corrections <= corrections)))
                conflicting_corrections = any(
                    (field == other_field and value != other_value) or _different_selected_objects(field, other_field)
                    for field, value in corrections for other_field, other_value in other_corrections)
                conflicting_corrections = conflicting_corrections or _conflicting_http_errors(
                    str(issue.get("suggestion") or ""), str(other.get("suggestion") or ""))
                same_supported_rule = (issue.get("kb_grounded") and other.get("kb_grounded")
                                       and bool(set(issue.get("kb_refs") or []) & set(other.get("kb_refs") or [])))
                if (issue.get("dimension") == other.get("dimension")
                        and issue.get("evidence_quote") == other.get("evidence_quote")
                        and not conflicting_corrections
                        and (overlap >= 0.65 or (same_supported_rule and (
                            identical_corrections
                            or _same_http_error(str(issue.get("suggestion") or ""), str(other.get("suggestion") or ""))
                            or (same_correction and containment >= 0.5))))):
                    found = group
                    break
            if found is None:
                groups.append([member])
            else:
                found.append(member)
        clusters.extend((key, group) for group in groups)
    candidates: list[CandidateRecord] = []
    for candidate_no, ((step_index, category), members) in enumerate(clusters, start=1):
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
        evidence_refs: dict[str, dict[str, Any]] = {}
        for _, issue in members:
            for ref in issue.get("evidence_refs") or []:
                if isinstance(ref, str):
                    evidence_refs.setdefault(ref, {"ref_id": ref, "verified": True})
                elif isinstance(ref, dict):
                    key = str(ref.get("ref_id") or ref.get("id") or len(evidence_refs))
                    evidence_refs.setdefault(key, ref)
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
                evidence_refs=list(evidence_refs.values()),
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
                    "rule": "same_step_category_dimension_quote_and_similar_claim_or_identical_grounded_correction",
                },
                category=category,
            )
        )
    return candidates
