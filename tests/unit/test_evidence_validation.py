"""Evidence 服务端校验：模型声明不能直接成为 grounded。"""

from __future__ import annotations

import pytest

from app.llm.evidence import quote_in_case, verify_evidence


def _issue(**overrides):
    base = {
        "step_index": 1,
        "dimension": "test_design",
        "severity": "major",
        "category": "预期不明确",
        "evidence_quote": "点击【发现】按钮",
        "rationale": "没有可判定的预期",
        "evidence_type": "testing_standard",
        "evidence_strength": "medium",
        "evidence_status": "grounded",
        "kb_grounded": False,
        "kb_refs": [],
        "evidence_refs": [],
    }
    base.update(overrides)
    return base


CASE = {
    "case_id": "TC-1",
    "title": "挖宝",
    "steps": [
        {"index": 1, "action": "点击【发现】按钮", "expected": "获得随机物品"},
    ],
}


def test_quote_matching_ignores_whitespace_but_not_content() -> None:
    assert quote_in_case("点击【发现】 按钮", "点击【发现】按钮")[0] is True
    assert quote_in_case("原文没有这句", "点击【发现】按钮")[0] is False
    assert quote_in_case("短", "点击【发现】按钮")[1] == "too_short"


def test_grounded_without_kb_refs_is_downgraded() -> None:
    result = verify_evidence(_issue(), CASE)
    assert result.status == "partially_grounded"
    assert result.kb_grounded is False
    assert "model_grounded_downgraded" in result.warnings
    assert result.validation_status == "needs_review"


def test_invalid_kb_ref_is_insufficient() -> None:
    result = verify_evidence(
        _issue(kb_grounded=True, kb_refs=["kb-fake"], evidence_type="business_rule"),
        CASE,
    )
    assert result.status == "insufficient"
    assert result.kb_grounded is False
    assert "kb_refs_not_in_pack" in result.warnings


def test_valid_kb_ref_can_be_grounded() -> None:
    result = verify_evidence(
        _issue(kb_grounded=True, kb_refs=["kb-1"], evidence_type="business_rule"),
        CASE,
        allowed_kb_refs={"kb-1"},
    )
    assert result.status == "grounded"
    assert result.kb_grounded is True
    assert result.kb_refs == ["kb-1"]


def test_missing_quote_never_grounded() -> None:
    result = verify_evidence(
        _issue(evidence_quote=None, evidence_type="testing_standard"), CASE
    )
    assert result.status == "ungrounded"
    assert result.evidence_support_status == "unsupported"
    assert "evidence_quote_missing" in result.warnings


@pytest.mark.parametrize("quote", [None, "用例中没有出现的操作", "短", "opaque-negative-case-label"])
def test_valid_knowledge_cannot_ground_an_absent_case_quote_or_management_label(quote):
    case = {**CASE, "case_id": "opaque-negative-case-label"}
    knowledge = {"chunk_id": "kb-1", "text": "每次点击发现按钮会获得随机物品", "evidence_level": "E2",
                 "knowledge_type": "BUSINESS_RULE"}
    result = verify_evidence(_issue(evidence_quote=quote, kb_grounded=True, kb_refs=["kb-1"],
                                   kb_quote=knowledge["text"], evidence_type="business_rule"),
                             case, allowed_kb_refs={"kb-1"}, knowledge_evidence=[knowledge])
    assert result.status == "insufficient" and not result.kb_grounded
    assert result.validation_status == "needs_review"


def test_inference_with_quote_is_ungrounded() -> None:
    result = verify_evidence(
        _issue(evidence_type="inference", evidence_status="grounded"), CASE
    )
    assert result.status == "ungrounded"
    assert result.evidence_support_status == "unsupported"
