"""Fusion 必须保留上游已验证的 evidence_refs，并去重。"""

from __future__ import annotations

from app.llm.base import ReviewOpinion
from app.pipeline.fusion import fuse


def _issue(role: str, refs: list[str]) -> dict:
    return {
        "step_index": 1,
        "dimension": "test_design",
        "severity": "major",
        "category": "预期不明确",
        "evidence_quote": "点击【发现】按钮",
        "rationale": f"{role} 认为缺少可判定预期",
        "suggestion": "补充背包数量变化",
        "kb_grounded": False,
        "kb_refs": [],
        "evidence_refs": refs,
        "evidence_type": "testing_standard",
        "evidence_strength": "medium",
        "evidence_status": "partially_grounded",
        "model_evidence_status": "partially_grounded",
        "evidence_support_status": "insufficient",
        "validation_status": "passed",
        "parse_warnings": [],
    }


def test_fusion_preserves_and_dedupes_evidence_refs() -> None:
    opinions = [
        ReviewOpinion(role="chief_blind", summary="", issues=[_issue("chief", ["e1"])]),
        ReviewOpinion(role="jury_a", summary="", issues=[_issue("jury", ["e1", "e2"])]),
    ]
    candidates = fuse("r1", {"steps": [{"index": 1, "action": "点击【发现】按钮"}]}, opinions)
    assert len(candidates) == 1
    refs = candidates[0].evidence_refs
    assert [item["ref_id"] for item in refs] == ["e1", "e2"]
    assert all(item["verified"] is True for item in refs)
    # 融合不得提升证据等级
    assert candidates[0].evidence_status == "partially_grounded"
