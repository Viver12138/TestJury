"""Evidence 服务端校验（docs/18 §1.1 L2–L4）。

原则：
- 模型输出的 `evidence_status` 只作为“模型声明”，不直接进入报告；
- 服务端校验引用是否存在、原文引用是否可回查，再生成最终 `evidence_status`；
- 没有知识库/证据包时，最高只能到 `partially_grounded`（测试设计规范），不能到 `grounded`；
- 校验失败不抛出整份输出，而是降级该条 issue 并记 parse_warning。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.enums import EvidenceStrength, EvidenceType

_SPACE = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _SPACE.sub("", text).lower()


def case_corpus(case: dict[str, Any]) -> str:
    parts: list[str] = [
        str(case.get("title") or ""),
        str(case.get("module") or ""),
    ]
    for step in case.get("steps") or []:
        parts.append(str(step.get("action") or ""))
        parts.append(str(step.get("expected") or ""))
    parts.extend(str(item) for item in case.get("preconditions") or [])
    parts.append(json.dumps(case.get("test_data"), ensure_ascii=False))
    parts.append(str(case.get("raw_text") or ""))
    return _norm(" ".join(parts))


def quote_in_case(quote: Any, corpus: str) -> tuple[bool, str | None]:
    if quote is None:
        return False, "missing"
    if not isinstance(quote, str):
        return False, "not_string"
    cleaned = _norm(quote)
    if len(cleaned) < 4:
        return False, "too_short"
    return (cleaned in corpus, "ok" if cleaned in corpus else "not_found")


def _string_list(value: Any) -> tuple[list[str], bool]:
    if value is None:
        return [], True
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return [], False
    return [item for item in value if item], True


@dataclass
class EvidenceResult:
    status: str
    kb_grounded: bool
    model_status: str | None
    evidence_support_status: str | None
    validation_status: str
    evidence_refs: list[str] = field(default_factory=list)
    kb_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def verify_evidence(
    issue: dict[str, Any],
    case: dict[str, Any],
    *,
    allowed_kb_refs: set[str] | None = None,
    allowed_evidence_refs: set[str] | None = None,
    knowledge_evidence: list[dict[str, Any]] | None = None,
) -> EvidenceResult:
    allowed_kb = allowed_kb_refs or set()
    allowed_evidence = allowed_evidence_refs or set()
    warnings: list[str] = []

    model_status = issue.get("evidence_status")
    evidence_type = str(issue.get("evidence_type") or EvidenceType.INFERENCE.value)
    strength = str(issue.get("evidence_strength") or EvidenceStrength.WEAK.value)
    quote = issue.get("evidence_quote")
    evidence_refs, refs_ok = _string_list(issue.get("evidence_refs"))
    kb_refs, kb_ok = _string_list(issue.get("kb_refs"))
    if not refs_ok:
        warnings.append("evidence_refs_invalid_type")
        evidence_refs = []
    if not kb_ok:
        warnings.append("kb_refs_invalid_type")
        kb_refs = []

    valid_evidence_refs = [ref for ref in evidence_refs if ref in allowed_evidence]
    invalid_evidence_refs = [ref for ref in evidence_refs if ref not in allowed_evidence]
    valid_kb_refs = [ref for ref in kb_refs if ref in allowed_kb]
    invalid_kb_refs = [ref for ref in kb_refs if ref not in allowed_kb]
    if invalid_evidence_refs:
        warnings.append("evidence_refs_not_in_pack")
    if invalid_kb_refs:
        warnings.append("kb_refs_not_in_pack")

    quote_ok, quote_reason = quote_in_case(quote, case_corpus(case))
    if quote_reason != "ok":
        warnings.append(f"evidence_quote_{quote_reason}")

    claimed_grounded = bool(issue.get("kb_grounded", False))
    kb_grounded = claimed_grounded and bool(valid_kb_refs)
    if claimed_grounded and not valid_kb_refs:
        warnings.append("kb_grounded_without_valid_refs")

    invalid_citation = bool(invalid_evidence_refs or invalid_kb_refs or (valid_kb_refs and not quote_ok))
    if valid_kb_refs and knowledge_evidence is not None:
        documents = {c["chunk_id"]: c for c in knowledge_evidence}
        kb_quote = issue.get("kb_quote")
        expected_types = {
            "business_rule": {"BUSINESS_RULE", "WORKFLOW"},
            "requirement": {"REQUIREMENT", "INTERFACE"},
            "known_limit": {"KNOWN_LIMITATION", "AUTOMATION"},
        }
        valid_quote = isinstance(kb_quote, str) and len(kb_quote.strip()) >= 8
        for ref in valid_kb_refs:
            doc = documents.get(ref, {})
            if (not valid_quote or kb_quote not in doc.get("text", "")
                    or doc.get("evidence_level") not in {"E1", "E2"}
                    or doc.get("knowledge_type") not in expected_types.get(evidence_type, set())):
                invalid_citation = True
        if invalid_citation:
            warnings.append("kb_quote_or_evidence_scope_unverified")
            kb_grounded = False

    if invalid_citation:
        status = "insufficient"
        kb_grounded = False
    elif valid_kb_refs and evidence_type in (
        EvidenceType.BUSINESS_RULE.value,
        EvidenceType.REQUIREMENT.value,
        EvidenceType.KNOWN_LIMIT.value,
    ):
        status = "grounded"
    elif quote_ok and evidence_type == EvidenceType.TESTING_STANDARD.value and strength in (
        EvidenceStrength.STRONG.value,
        EvidenceStrength.MEDIUM.value,
    ):
        status = "partially_grounded"
    elif quote_ok and evidence_type == EvidenceType.INFERENCE.value:
        status = "ungrounded"
    elif quote_ok and evidence_type in (
        EvidenceType.REQUIREMENT.value,
        EvidenceType.BUSINESS_RULE.value,
        EvidenceType.KNOWN_LIMIT.value,
        EvidenceType.HISTORICAL_BUG.value,
    ):
        status = "insufficient"
    else:
        status = "ungrounded"

    # 模型声明不能直接成为服务端结论；冲突/grounded 都需要外部证据包
    if model_status == "conflicted":
        warnings.append("model_conflict_unverified")
    if model_status == "grounded" and status != "grounded":
        warnings.append("model_grounded_downgraded")

    # `evidence_support_status` 是服务端验证后的支持结果，不是模型声明；
    # 模型原始声明保存在 `model_evidence_status`。
    support_map = {
        "grounded": "supported",
        "partially_grounded": "insufficient",
        "ungrounded": "unsupported",
        "conflicted": "conflicted",
        "insufficient": "insufficient",
    }
    support = support_map.get(status)
    validation = "needs_review" if warnings else "passed"
    return EvidenceResult(
        status=status,
        kb_grounded=kb_grounded,
        model_status=str(model_status) if model_status else None,
        evidence_support_status=support,
        validation_status=validation,
        evidence_refs=valid_evidence_refs,
        kb_refs=valid_kb_refs,
        warnings=warnings,
    )
