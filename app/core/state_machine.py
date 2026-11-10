"""任务/阶段/复核任务状态机（docs/10 §8.1、docs/13 §1、§5.3、docs/09 §12.2）。

- 非法迁移必须抛 `IllegalTransition`，调用方不得先写库再校验。
- 状态值来自 `app.core.enums`，与 docs/17 同源。
- fencing token 校验：旧 Worker 的写入必须被拒绝（docs/13 §5.2）。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import ReviewStatus, ReviewTaskStatus, StageStatus

TERMINAL_REVIEW_STATUSES = frozenset(
    {
        ReviewStatus.DONE.value,
        ReviewStatus.COMPLETED_WITH_WARNINGS.value,
        ReviewStatus.FAILED.value,
        ReviewStatus.CANCELLED.value,
    }
)

REVIEW_TRANSITIONS: dict[str, frozenset[str]] = {
    ReviewStatus.QUEUED.value: frozenset({ReviewStatus.PROCESSING.value}),
    ReviewStatus.PROCESSING.value: frozenset(
        {
            ReviewStatus.RETRYING.value,
            ReviewStatus.DONE.value,
            ReviewStatus.COMPLETED_WITH_WARNINGS.value,
            ReviewStatus.FAILED.value,
            ReviewStatus.CANCELLED.value,
        }
    ),
    ReviewStatus.RETRYING.value: frozenset(
        {ReviewStatus.PROCESSING.value, ReviewStatus.FAILED.value, ReviewStatus.CANCELLED.value}
    ),
    ReviewStatus.DONE.value: frozenset(),
    ReviewStatus.COMPLETED_WITH_WARNINGS.value: frozenset(),
    ReviewStatus.FAILED.value: frozenset(),
    ReviewStatus.CANCELLED.value: frozenset(),
}

STAGE_TRANSITIONS: dict[str, frozenset[str]] = {
    StageStatus.PENDING.value: frozenset({StageStatus.RUNNING.value, StageStatus.SKIPPED.value}),
    StageStatus.RUNNING.value: frozenset({StageStatus.SUCCEEDED.value, StageStatus.FAILED.value}),
    StageStatus.FAILED.value: frozenset({StageStatus.RUNNING.value}),
    StageStatus.SUCCEEDED.value: frozenset(),
    StageStatus.SKIPPED.value: frozenset(),
}

REVIEW_TASK_TRANSITIONS: dict[str, frozenset[str]] = {
    ReviewTaskStatus.PENDING.value: frozenset(
        {ReviewTaskStatus.IN_PROGRESS.value, ReviewTaskStatus.CANCELLED.value}
    ),
    ReviewTaskStatus.IN_PROGRESS.value: frozenset(
        {ReviewTaskStatus.COMPLETED.value, ReviewTaskStatus.CANCELLED.value}
    ),
    # 重开：completed -> in_progress（docs/09 §12.2）；不存在 completed -> pending
    ReviewTaskStatus.COMPLETED.value: frozenset({ReviewTaskStatus.IN_PROGRESS.value}),
    ReviewTaskStatus.CANCELLED.value: frozenset({ReviewTaskStatus.IN_PROGRESS.value}),
}


class IllegalTransition(Exception):
    def __init__(self, entity: str, current: str, target: str) -> None:
        self.entity = entity
        self.current = current
        self.target = target
        super().__init__(f"{entity} 不允许从 {current!r} 迁移到 {target!r}")


class FencingMismatch(Exception):
    """当前 Worker 已失去执行权（租约被接管）。"""

    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"fencing token 不匹配：期望 {expected}，数据库为 {actual}；停止写入")


@dataclass(frozen=True)
class Fencing:
    """fencing token 语义：仅所有权转移时递增，正常续租不变。"""

    token: int

    def valid_for(self, row_token: int) -> bool:
        return row_token == self.token


def _check(
    transitions: dict[str, frozenset[str]],
    entity: str,
    current: str,
    target: str,
) -> str:
    allowed = transitions.get(current)
    if allowed is None or target not in allowed:
        raise IllegalTransition(entity, current, target)
    return target


def check_review_transition(current: str, target: str) -> str:
    return _check(REVIEW_TRANSITIONS, "review_job", current, target)


def check_stage_transition(current: str, target: str) -> str:
    return _check(STAGE_TRANSITIONS, "review_stage", current, target)


def check_review_task_transition(current: str, target: str) -> str:
    return _check(REVIEW_TASK_TRANSITIONS, "human_review_task", current, target)


def is_terminal_review_status(status: str) -> bool:
    return status in TERMINAL_REVIEW_STATUSES


def check_fencing(row_token: int, expected_token: int) -> None:
    """写入前校验租约令牌；不匹配说明执行权已转移，必须停止写入。"""

    if row_token != expected_token:
        raise FencingMismatch(expected_token, row_token)
