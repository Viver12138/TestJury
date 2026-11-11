"""真实评审适配器的解析与信任边界（Fake ChatAdapter，不调用供应商）。"""

from __future__ import annotations

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


@pytest.mark.asyncio
async def test_review_parses_issues_and_drops_decision_fields() -> None:
    content = json.dumps(
        {
            "role": "chief_blind",
            "ai_verdict": "approved",
            "overall": {"comment": "整体可执行，但第 3 步缺预期"},
            "issues": [
                {
                    "step_index": 3,
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
        "chief_blind", {"case_id": "TC-1", "steps": [{"index": 1, "action": "a"}]}
    )

    assert opinion.summary.startswith("整体可执行")
    assert len(opinion.issues) == 1
    assert opinion.issues[0]["severity"] == "major"
    assert opinion.issues[0]["kb_grounded"] is False
    assert opinion.model == "fake-model-2026-11"
    assert opinion.input_tokens == 120
    assert opinion.cost_estimate is not None
    assert any("ai_verdict" in warning for warning in opinion.warnings)

    request = adapter.requests[0]
    assert "评审标准" in request.messages[1].content
    assert "TC-1" in request.messages[1].content
    assert request.temperature == ModelRegistry.load(MODELS_PATH).role("chief_blind").temperature
    assert request.max_tokens == ModelRegistry.load(MODELS_PATH).role("chief_blind").max_output_tokens


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
async def test_vote_parses_and_enforces_validity_rules() -> None:
    model, _ = _model(json.dumps({"validity": "reject", "severity": "blocker", "reason": "不成立"}))
    decision = await model.vote("jury_a", {"description": "第 3 步缺预期"})
    assert decision.validity == "reject"
    assert decision.severity is None
    assert decision.reason == "不成立"

    model, _ = _model(json.dumps({"validity": "accept", "severity": "major"}))
    decision = await model.vote("jury_a", {"description": "x"})
    assert decision.validity == "accept" and decision.severity == "major"

    model, _ = _model(json.dumps({"validity": "maybe"}))
    with pytest.raises(AdapterError):
        await model.vote("jury_a", {"description": "x"})
