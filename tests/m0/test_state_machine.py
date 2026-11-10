"""ACC-M0-018：任务/阶段/复核任务非法迁移被拒（纯状态机）。"""

from __future__ import annotations

import pytest

from app.core.state_machine import (
    FencingMismatch,
    IllegalTransition,
    check_fencing,
    check_review_task_transition,
    check_review_transition,
    check_stage_transition,
    is_terminal_review_status,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("done", "processing"),
        ("cancelled", "processing"),
        ("queued", "done"),
        ("completed_with_warnings", "queued"),
        ("failed", "retrying"),
    ],
)
def test_illegal_review_transitions_are_rejected(current: str, target: str) -> None:
    with pytest.raises(IllegalTransition):
        check_review_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("queued", "processing"),
        ("processing", "done"),
        ("processing", "completed_with_warnings"),
        ("processing", "retrying"),
        ("retrying", "processing"),
        ("retrying", "failed"),
    ],
)
def test_legal_review_transitions_pass(current: str, target: str) -> None:
    assert check_review_transition(current, target) == target


def test_terminal_statuses() -> None:
    assert is_terminal_review_status("done")
    assert is_terminal_review_status("completed_with_warnings")
    assert is_terminal_review_status("failed")
    assert is_terminal_review_status("cancelled")
    assert not is_terminal_review_status("processing")


@pytest.mark.parametrize(
    ("current", "target"),
    [("succeeded", "running"), ("skipped", "running"), ("pending", "succeeded")],
)
def test_illegal_stage_transitions_are_rejected(current: str, target: str) -> None:
    with pytest.raises(IllegalTransition):
        check_stage_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("pending", "running"),
        ("pending", "skipped"),
        ("running", "succeeded"),
        ("running", "failed"),
        ("failed", "running"),
    ],
)
def test_legal_stage_transitions_pass(current: str, target: str) -> None:
    assert check_stage_transition(current, target) == target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("completed", "pending"),
        ("pending", "completed"),
        ("completed", "cancelled"),
    ],
)
def test_illegal_review_task_transitions_are_rejected(current: str, target: str) -> None:
    with pytest.raises(IllegalTransition):
        check_review_task_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("pending", "in_progress"),
        ("in_progress", "completed"),
        ("completed", "in_progress"),
        ("cancelled", "in_progress"),
    ],
)
def test_legal_review_task_transitions_pass(current: str, target: str) -> None:
    assert check_review_task_transition(current, target) == target


def test_fencing_mismatch_is_detected() -> None:
    check_fencing(2, 2)
    with pytest.raises(FencingMismatch):
        check_fencing(2, 1)
