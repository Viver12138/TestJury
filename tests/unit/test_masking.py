"""真实脱敏：发送给 Adapter 的内容不得含原始 PII/密钥。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.llm.base import ChatResponse, TokenUsage
from app.llm.masking import MaskingPolicy
from app.llm.registry import ModelRegistry
from app.llm.review import ChatReviewModel
from app.rubric.loader import RubricRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS = REPO_ROOT / "config" / "models.yaml"


class RecordingAdapter:
    def __init__(self) -> None:
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ChatResponse(
            text=json.dumps({"overall": {"comment": "ok"}, "issues": []}),
            model="fake",
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            latency_ms=1,
            raw={},
        )

    async def aclose(self) -> None:
        return None


def _model(adapter, policy):
    registry = ModelRegistry.load(MODELS)
    rubric = RubricRepository(
        REPO_ROOT / "rubric" / "rubric.yaml", REPO_ROOT / "rubric" / "schema.json"
    ).load_active()
    return ChatReviewModel(registry, {"chief_blind": adapter}, rubric=rubric, masking_policy=policy)


def test_mask_text_and_secret_fields() -> None:
    policy = MaskingPolicy()
    result = policy.apply(
        {
            "title": "用户 alice@example.com 手机 13800138000",
            "test_data": {"password": "P@ssw0rd", "email": "bob@example.com"},
        }
    )
    text = json.dumps(result.data, ensure_ascii=False)
    assert "alice@example.com" not in text
    assert "bob@example.com" not in text
    assert "13800138000" not in text
    assert "P@ssw0rd" not in text
    assert "<EMAIL_1>" in text and "<PHONE_1>" in text
    assert result.report["policy_id"] == "mask-pii-v1"
    assert result.report["total"] >= 3


def test_numeric_and_camel_case_sensitive_values_are_masked() -> None:
    policy = MaskingPolicy()
    result = policy.apply(
        {
            "phoneNumber": 13800138000,
            "password": 123456,
            "accessToken": "tok-123",
            "nested": [{"id_card": 110101199001011234}],
        }
    )
    text = json.dumps(result.data, ensure_ascii=False)
    assert "13800138000" not in text
    assert "123456" not in text
    assert "tok-123" not in text
    assert "110101199001011234" not in text
    assert result.data["phoneNumber"].startswith("<PII_")
    assert result.data["password"].startswith("<SECRET_")
    assert result.data["accessToken"].startswith("<SECRET_")


def test_prefixed_and_suffixed_sensitive_field_names() -> None:
    policy = MaskingPolicy()
    result = policy.apply(
        {
            "userEmail": "alice@example.com",
            "contactPhone": "13800138000",
            "fullName": "张三",
            "customerName": "李四",
            "billingAddress": "北京市朝阳区某路 1 号",
            "authToken": "tok-abc",
            "clientSecret": "sec-xyz",
            "dbPassword": "db-pass",
        }
    )
    text = json.dumps(result.data, ensure_ascii=False)
    for raw in (
        "alice@example.com",
        "13800138000",
        "张三",
        "李四",
        "北京市朝阳区某路 1 号",
        "tok-abc",
        "sec-xyz",
        "db-pass",
    ):
        assert raw not in text
    assert all(str(value).startswith("<") for value in result.data.values())


@pytest.mark.asyncio
async def test_adapter_receives_masked_case() -> None:
    adapter = RecordingAdapter()
    policy = MaskingPolicy()
    model = _model(adapter, policy)
    case = {
        "case_id": "TC-MASK-001",
        "title": "登录 alice@example.com",
        "steps": [
            {
                "index": 1,
                "action": "用 alice@example.com / P@ssw0rd 登录",
                "expected": "登录成功",
            }
        ],
        "test_data": {"password": "P@ssw0rd", "email": "alice@example.com"},
    }
    opinion = await model.review("chief_blind", case)
    sent = json.dumps(
        [{"role": message.role, "content": message.content} for message in adapter.requests[0].messages],
        ensure_ascii=False,
    )
    assert "alice@example.com" not in sent
    assert "P@ssw0rd" not in sent
    assert "<EMAIL_1>" in sent and "<SECRET_1>" in sent
    assert opinion.masking_policy_id == "mask-pii-v1"
    assert opinion.masking_policy_version == "1.0"
    assert opinion.masking_report["applied"] is True


@pytest.mark.asyncio
async def test_no_policy_sends_original() -> None:
    adapter = RecordingAdapter()
    model = _model(adapter, None)
    await model.review(
        "chief_blind",
        {"case_id": "TC-RAW", "steps": [{"index": 1, "action": "alice@example.com", "expected": "x"}]},
    )
    sent = adapter.requests[0].messages[1].content
    assert "alice@example.com" in sent
