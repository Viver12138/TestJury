"""真实评审适配器的解析与信任边界（Fake ChatAdapter，不调用供应商）。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.llm.base import AdapterError, ChatResponse, TokenUsage
from app.llm.registry import ModelRegistry
from app.llm.review import ChatReviewModel
from app.rubric.loader import RubricRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_PATH = REPO_ROOT / "config" / "models.yaml"


class FakeChatAdapter:
    def __init__(self, content: str) -> None:
        self.content = content
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ChatResponse(
            text=self.content,
            model="fake-model-2026-11",
            usage=TokenUsage(input_tokens=120, output_tokens=30),
            latency_ms=88,
            raw={},
        )

    async def aclose(self) -> None:
        return None


def _model(content: str) -> tuple[ChatReviewModel, FakeChatAdapter]:
    registry = ModelRegistry.load(MODELS_PATH)
    rubric = RubricRepository(
        REPO_ROOT / "rubric" / "rubric.yaml", REPO_ROOT / "rubric" / "schema.json"
    ).load_active()
    adapter = FakeChatAdapter(content)
    model = ChatReviewModel(
        registry,
        {role: adapter for role in ("chief_blind", "jury_a", "jury_b")},
        rubric=rubric,
    )
    return model, adapter


async def test_arbitration_requires_exact_candidate_coverage_and_keeps_case_context():
    candidates = [{"candidate_id": "c1", "description": "冲突", "case": {"title": "金额计算"}},
                  {"candidate_id": "c2", "description": "另一个冲突"}]
    model, adapter = _model(json.dumps({"decisions": [
        {"candidate_id": "c1", "chief_decision": "adopt", "chief_reason": "依据明确"}]}))
    with pytest.raises(AdapterError, match="候选集合不完整"):
        await model.arbitrate(candidates, None)
    material = json.loads(adapter.requests[0].messages[-1].content)
    assert material["candidates"][0]["case"]["title"] == "金额计算"
    adapter.content = json.dumps({"decisions": [
        {"candidate_id": c["candidate_id"], "chief_decision": "need_human", "chief_reason": "依据不足"}
        for c in candidates]})
    decisions, _ = await model.arbitrate(candidates, None)
    assert set(decisions) == {"c1", "c2"}


@pytest.mark.asyncio
async def test_review_parses_issues_and_drops_decision_fields() -> None:
    content = json.dumps(
        {
            "role": "chief_blind",
            "ai_verdict": "approved",
            "overall": {"comment": "整体可执行，但第 3 步缺预期"},
            "issues": [
                {
                    "scope": "step", "step_index": 3,
                    "dimension": "test_design",
                    "severity": "major",
                    "category": "预期不明确",
                    "evidence_quote": "点击【发现】按钮",
                    "rationale": "没有可判定的预期结果",
                    "suggestion": "补充背包物品数量变化",
                    "kb_grounded": False,
                    "evidence_type": "testing_standard",
                    "evidence_strength": "medium",
                    "evidence_status": "grounded",
                }
            ],
        },
        ensure_ascii=False,
    )
    model, adapter = _model(content)
    opinion = await model.review(
        "chief_blind",
        {
            "case_id": "TC-1",
            "steps": [
                {"index": 1, "action": "a", "expected": "x"},
                {"index": 2, "action": "b", "expected": "y"},
                {"index": 3, "action": "点击【发现】按钮", "expected": "z"},
            ],
        },
    )

    assert opinion.summary.startswith("整体可执行")
    assert len(opinion.issues) == 1
    assert opinion.issues[0]["severity"] == "major"
    assert opinion.issues[0]["kb_grounded"] is False
    assert opinion.issues[0]["evidence_status"] == "partially_grounded"
    assert opinion.issues[0]["model_evidence_status"] == "grounded"
    assert opinion.model == "fake-model-2026-11"
    assert opinion.input_tokens == 120
    assert opinion.cost_estimate is not None
    assert any("ai_verdict" in warning for warning in opinion.warnings)
    assert any("model_grounded_downgraded" in warning for warning in opinion.warnings)

    request = adapter.requests[0]
    assert "评审标准" in request.messages[1].content
    assert "TC-1" not in request.messages[1].content
    assert request.temperature == ModelRegistry.load(MODELS_PATH).role("chief_blind").temperature
    assert request.max_tokens == ModelRegistry.load(MODELS_PATH).role("chief_blind").max_output_tokens


async def test_management_labels_are_hidden_in_all_model_stages_but_business_ids_remain():
    case = {"case_id": "LABEL-negative-DO-NOT-REVIEW", "case_version": 987654321,
            "product_version": "1.0.0", "title": "Can this order be paid?",
            "steps": [{"index": 1, "action": "Pay order_id=12345", "expected": "status=PAID"}]}
    original = copy.deepcopy(case)
    model, adapter = _model(json.dumps({"overall": {"comment": "ok"}, "issues": []}))
    await model.review("chief_blind", case)
    adapter.content = json.dumps({"validity": "reject", "severity": None, "reason": "unsupported"})
    await model.vote("chief_blind", {"description": "question title", "case": case})
    adapter.content = json.dumps({"decisions": [{"candidate_id": "c1", "chief_decision": "reject",
                                               "chief_reason": "unsupported"}]})
    await model.arbitrate([{"candidate_id": "c1", "description": "question title", "case": case}], None)
    assert case == original
    for request in adapter.requests:
        material = request.messages[-1].content
        assert case["case_id"] not in material and "987654321" not in material
        assert "order_id=12345" in material and "1.0.0" in material


@pytest.mark.parametrize("kb_quote, expected", [
    ("服务端必须按商品单价计算订单金额", "grounded"),
    ("这段引文不在知识片段中，不得升级证据", "insufficient"),
])
async def test_kb_quote_is_retained_for_audit_without_upgrading_unverified_text(kb_quote, expected):
    issue = {"scope": "step", "step_index": 1, "dimension": "business", "severity": "major",
             "category": "规则冲突", "evidence_quote": "响应金额为零", "rationale": "金额与规则不符",
             "suggestion": "按商品单价计算", "kb_grounded": True, "kb_refs": ["r1"], "evidence_refs": ["r1"],
             "kb_quote": kb_quote, "evidence_type": "business_rule", "evidence_strength": "strong",
             "evidence_status": "grounded"}
    case = {"steps": [{"index": 1, "action": "创建订单", "expected": "响应金额为零"}],
            "_knowledge_pack": {"baseline": {"type": "current_implementation"}, "build_version": "test",
                                "evidence": [{"chunk_id": "r1", "doc_id": "RULE-1", "knowledge_type": "BUSINESS_RULE",
                                              "evidence_level": "E2", "heading_path": "金额规则",
                                              "text": "服务端必须按商品单价计算订单金额"}]}}
    model, _ = _model(json.dumps({"overall": {"comment": "金额冲突"}, "issues": [issue]}, ensure_ascii=False))
    opinion = await model.review("chief_blind", case)
    assert opinion.issues[0]["kb_quote"] == kb_quote
    assert opinion.issues[0]["evidence_status"] == expected
    assert opinion.issues[0]["kb_grounded"] == (expected == "grounded")


@pytest.mark.asyncio
async def test_kimi_role_uses_temperature_one() -> None:
    model, adapter = _model(
        json.dumps({"role": "jury_b", "overall": {"comment": "ok"}, "issues": []})
    )
    await model.review("jury_b", {"case_id": "TC-2", "steps": []})
    request = adapter.requests[0]
    config = ModelRegistry.load(MODELS_PATH).role("jury_b")
    assert request.temperature == 1.0
    assert request.max_tokens == config.max_output_tokens


@pytest.mark.asyncio
async def test_invalid_model_output_is_rejected() -> None:
    model, _ = _model("not-json")
    with pytest.raises(AdapterError) as excinfo:
        await model.review("chief_blind", {"case_id": "TC-3", "steps": []})
    assert excinfo.value.code == "OUTPUT_INVALID"

    missing_rationale = json.dumps({"overall": {"comment": "x"}, "issues": [{"severity": "major"}]})
    model, _ = _model(missing_rationale)
    with pytest.raises(AdapterError):
        await model.review("chief_blind", {"case_id": "TC-4", "steps": []})


@pytest.mark.asyncio
async def test_vote_rejects_severity_on_non_accept_and_invalid_severity() -> None:
    model, _ = _model(json.dumps({"validity": "reject", "severity": "blocker", "reason": "不成立"}))
    with pytest.raises(AdapterError):
        await model.vote("jury_a", {"description": "第 3 步缺预期"})

    model, _ = _model(json.dumps({"validity": "accept", "severity": "major", "reason": "成立"}))
    decision = await model.vote("jury_a", {"description": "x"})
    assert decision.validity == "accept" and decision.severity == "major"

    model, _ = _model(json.dumps({"validity": "accept", "severity": "严重"}))
    with pytest.raises(AdapterError):
        await model.vote("jury_a", {"description": "x"})

    model, _ = _model(json.dumps({"validity": "maybe"}))
    with pytest.raises(AdapterError):
        await model.vote("jury_a", {"description": "x"})


@pytest.mark.asyncio
async def test_invalid_issue_enum_drops_issue_instead_of_downgrading() -> None:
    base = {
        "scope": "step", "step_index": 1,
        "dimension": "test_design",
        "severity": "major",
        "category": "预期不明确",
        "evidence_quote": "a",
        "rationale": "缺预期",
        "suggestion": "补预期",
        "kb_grounded": False,
        "evidence_type": "testing_standard",
        "evidence_strength": "medium",
        "evidence_status": "partially_grounded",
    }
    bad = dict(base, severity="严重")
    good = dict(base, category="前置不足")
    content = json.dumps({"overall": {"comment": "ok"}, "issues": [bad, good]}, ensure_ascii=False)
    model, _ = _model(content)
    opinion = await model.review(
        "chief_blind", {"case_id": "TC-ENUM", "steps": [{"index": 1, "action": "a"}]}
    )
    assert len(opinion.issues) == 1
    assert opinion.issues[0]["category"] == "前置不足"
    assert any("issue_dropped:0:severity_invalid" in warning for warning in opinion.warnings)

    all_bad = json.dumps({"overall": {"comment": "x"}, "issues": [bad]}, ensure_ascii=False)
    model, _ = _model(all_bad)
    with pytest.raises(AdapterError):
        await model.review(
            "chief_blind", {"case_id": "TC-ENUM2", "steps": [{"index": 1, "action": "a"}]}
        )


@pytest.mark.asyncio
async def test_evidence_quote_must_exist_and_grounded_is_not_trusted() -> None:
    issue = {
        "scope": "step", "step_index": 1,
        "dimension": "test_design",
        "severity": "blocker",
        "category": "预期不明确",
        "evidence_quote": "原文中不存在的句子",
        "rationale": "缺预期",
        "suggestion": "补预期",
        "kb_grounded": True,
        "kb_refs": ["kb-fake-1"],
        "evidence_type": "business_rule",
        "evidence_strength": "strong",
        "evidence_status": "grounded",
    }
    content = json.dumps({"overall": {"comment": "x"}, "issues": [issue]}, ensure_ascii=False)
    model, _ = _model(content)
    opinion = await model.review(
        "chief_blind", {"case_id": "TC-EVID", "steps": [{"index": 1, "action": "a"}]}
    )
    result = opinion.issues[0]
    assert result["evidence_status"] == "insufficient"
    assert result["validation_status"] == "needs_review"
    assert result["kb_grounded"] is False
    assert any("evidence_quote_not_found" in warning for warning in opinion.warnings)
    assert any("kb_refs_not_in_pack" in warning for warning in opinion.warnings)


@pytest.mark.asyncio
async def test_case_scope_issue_requires_null_step_index() -> None:
    base = {
        "scope": "case",
        "step_index": None,
        "dimension": "test_design",
        "severity": "major",
        "category": "覆盖缺失",
        "evidence_quote": None,
        "rationale": "整个用例缺少边界场景",
        "suggestion": "补充边界场景",
        "kb_grounded": False,
        "evidence_type": "testing_standard",
        "evidence_strength": "medium",
        "evidence_status": "ungrounded",
    }
    content = json.dumps({"overall": {"comment": "x"}, "issues": [base]}, ensure_ascii=False)
    model, _ = _model(content)
    opinion = await model.review("chief_blind", {"case_id": "TC-CASE", "steps": []})
    assert opinion.issues[0]["scope"] == "case"
    assert opinion.issues[0]["step_index"] is None

    bad = dict(base, step_index=1)
    model, _ = _model(
        json.dumps({"overall": {"comment": "x"}, "issues": [bad]}, ensure_ascii=False)
    )
    with pytest.raises(AdapterError):
        await model.review("chief_blind", {"case_id": "TC-CASE2", "steps": [{"index": 1, "action": "a"}]})


@pytest.mark.asyncio
async def test_step_scope_requires_quote() -> None:
    issue = {
        "scope": "step",
        "step_index": 1,
        "dimension": "test_design",
        "severity": "major",
        "category": "预期不明确",
        "evidence_quote": None,
        "rationale": "缺预期",
        "suggestion": "补预期",
        "kb_grounded": False,
        "evidence_type": "testing_standard",
        "evidence_strength": "medium",
        "evidence_status": "ungrounded",
    }
    model, _ = _model(
        json.dumps({"overall": {"comment": "x"}, "issues": [issue]}, ensure_ascii=False)
    )
    with pytest.raises(AdapterError):
        await model.review(
            "chief_blind", {"case_id": "TC-STEP", "steps": [{"index": 1, "action": "a"}]}
        )


def test_output_schema_has_no_role_field() -> None:
    from app.llm.review import _OUTPUT_SCHEMA

    assert '"role"' not in _OUTPUT_SCHEMA


@pytest.mark.asyncio
async def test_missing_issues_field_is_rejected() -> None:
    model, _ = _model(json.dumps({"overall": {"comment": "没有发现问题"}}))
    with pytest.raises(AdapterError):
        await model.review("chief_blind", {"case_id": "TC-MISS", "steps": []})

    model, _ = _model(json.dumps({"overall": {"comment": "x"}, "issues": None}))
    with pytest.raises(AdapterError):
        await model.review("chief_blind", {"case_id": "TC-NULL", "steps": []})


@pytest.mark.asyncio
async def test_invalid_category_and_types_are_dropped() -> None:
    base = {
        "scope": "step", "step_index": 1,
        "dimension": "test_design",
        "severity": "major",
        "category": "预期不明确",
        "evidence_quote": "a",
        "rationale": "缺预期",
        "suggestion": "补预期",
        "kb_grounded": False,
        "evidence_type": "testing_standard",
        "evidence_strength": "medium",
        "evidence_status": "partially_grounded",
    }
    bad_category = dict(base, category="不在枚举里的分类")
    bad_type = dict(base, category="前置不足", rationale={"not": "string"})
    good = dict(base, category="数据缺失")
    good2 = dict(base, category="边界缺失")
    content = json.dumps(
        {"overall": {"comment": "x"}, "issues": [bad_category, bad_type, good, good2]},
        ensure_ascii=False,
    )
    model, _ = _model(content)
    opinion = await model.review(
        "chief_blind", {"case_id": "TC-CAT", "steps": [{"index": 1, "action": "a"}]}
    )
    assert len(opinion.issues) == 2
    assert {item["category"] for item in opinion.issues} == {"数据缺失", "边界缺失"}
    assert any("category_invalid" in item for item in opinion.warnings)
    assert any("rationale_type" in item for item in opinion.warnings)
