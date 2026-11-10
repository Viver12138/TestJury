"""ACC-M0-013：决策字段信任边界。

模型输出携带 `ai_verdict=approved` / `human_status=approved` 时：
- 字段被丢弃并记 parse_warning（`sanitize_model_output`）；
- 报告 `ai_verdict` 仍由 `verdict.py` 计算；
- 人工状态不影响 AI 结论。
"""

from __future__ import annotations

from app.pipeline.validate import sanitize_model_output
from app.pipeline.verdict import compute_verdict


def test_decision_fields_are_dropped_recursively() -> None:
    raw = {
        "summary": "整体可执行",
        "ai_verdict": "approved",
        "human_status": "approved",
        "permissions": ["admin"],
        "issues": [
            {
                "candidate_id": "C1",
                "severity": "major",
                "rationale": "预期不明确",
                "status": "adopted",
                "role": "approver",
                "nested": {"approved": True},
            }
        ],
    }
    sanitized = sanitize_model_output(raw)
    assert "ai_verdict" not in sanitized.data
    assert "human_status" not in sanitized.data
    assert "permissions" not in sanitized.data
    issue = sanitized.data["issues"][0]
    assert "status" not in issue and "role" not in issue
    assert "approved" not in issue["nested"]
    assert any("dropped_model_field:ai_verdict" == warning for warning in sanitized.warnings)
    assert any("dropped_model_field:issues[0].status" == warning for warning in sanitized.warnings)


def test_model_claimed_verdict_does_not_reach_result() -> None:
    payload = {
        "participants": 3,
        "model_claimed_verdict": "approved",
        "human_status": "approved",
        "issues": [
            {
                "candidate_id": "C1",
                "votes": [["accept", "major"], ["accept", "major"], ["accept", "major"]],
                "evidence_status": "grounded",
                "ai_verdict": "approved",
            }
        ],
    }
    result = compute_verdict(payload)
    assert result.ai_verdict == "conditional"
    assert result.ai_verdict != "approved"


def test_model_output_cannot_raise_severity_with_core_role() -> None:
    """模型把 supporting 改成 core 抬高严重级：core 数量/证据不合法时必须拒绝或降级。"""

    # 两个 core → 输入非法，不能静默接受
    with_extra_core = {
        "participants": 3,
        "issues": [
            {
                "candidate_id": "C1",
                "votes": [["accept", "blocker"], ["accept", "blocker"], ["accept", "blocker"]],
                "claims": [
                    {"role": "core", "status": "supported", "level": "E2"},
                    {"role": "core", "status": "supported", "level": "E2"},
                ],
            }
        ],
    }
    import pytest

    from app.pipeline.verdict import VerdictInputError

    with pytest.raises(VerdictInputError):
        compute_verdict(with_extra_core)

    # core 只有 E4 → 无 E1/E2 → 不得判 blocker
    weak_core = {
        "participants": 3,
        "issues": [
            {
                "candidate_id": "C1",
                "votes": [["accept", "blocker"], ["accept", "blocker"], ["accept", "blocker"]],
                "claims": [{"role": "core", "status": "supported", "level": "E4"}],
            }
        ],
    }
    result = compute_verdict(weak_core)
    assert result.issue_statuses["C1"] == "need_human"
    assert result.ai_verdict == "need_human"
