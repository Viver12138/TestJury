"""ACC-M0-022：review_completeness 的 complete 语义（流程完整性 vs 参与度）。"""

from __future__ import annotations

import pytest

from app.pipeline.stages import STAGE_NAMES, build_completeness


def _states(**overrides: str) -> dict[str, str]:
    states = {name: "succeeded" for name in STAGE_NAMES}
    states.update(overrides)
    return states


def _build(states: dict[str, str], **kwargs):
    params = {
        "raw_text": False,
        "kb_covered": False,
        "arbitration_required": False,
        "blind": "3/3",
        "vote": "3/3",
        "arbitration": "skipped",
    }
    params.update(kwargs)
    return build_completeness(states, **params)


def test_conditional_skip_keeps_complete_true() -> None:
    result = _build(_states(arbitration="skipped", kb_retrieve="skipped", preprocess="skipped"))
    assert result["complete"] is True
    assert "arbitration" in result["stages_skipped"]
    assert "arbitration" not in result["stages_completed"]


def test_required_stage_skipped_is_incomplete() -> None:
    result = _build(_states(blind_review="skipped"))
    assert result["complete"] is False


def test_required_stage_failed_is_incomplete() -> None:
    result = _build(_states(vote="failed"))
    assert result["complete"] is False
    assert "vote" in result["stages_failed"]


def test_required_stage_pending_is_incomplete() -> None:
    result = _build(_states(render="pending"))
    assert result["complete"] is False
    assert "render" in result["stages_pending"]


def test_required_arbitration_skipped_is_incomplete() -> None:
    result = _build(_states(arbitration="skipped"), arbitration_required=True)
    assert result["complete"] is False


def test_two_of_three_participation_is_complete_but_not_full() -> None:
    result = _build(_states(arbitration="skipped"), blind="2/3", vote="2/3")
    assert result["complete"] is True
    assert result["full_participation"] is False


def test_full_participation_requires_both_blind_and_vote() -> None:
    assert _build(_states())["full_participation"] is True
    assert _build(_states(), vote="2/3")["full_participation"] is False


def test_stage_lists_partition_all_stages() -> None:
    result = _build(
        _states(
            preprocess="skipped",
            kb_retrieve="skipped",
            arbitration="skipped",
            vote="failed",
            render="pending",
        )
    )
    groups = [
        set(result["stages_completed"]),
        set(result["stages_skipped"]),
        set(result["stages_failed"]),
        set(result["stages_pending"]),
    ]
    union: set[str] = set()
    for group in groups:
        assert not (union & group), f"阶段重复计入: {union & group}"
        union |= group
    assert union == set(STAGE_NAMES)


def test_invalid_stage_status_is_rejected() -> None:
    with pytest.raises(ValueError):
        _build(_states(verdict="unknown"))
