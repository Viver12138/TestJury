"""阶段与 `review_completeness` 语义（docs/03 §2.1、docs/13 §5.3、ACC-M0-020/022）。

`complete` 只表示流程完整性：
- 必需阶段（始终必需 + 本次条件触发）全部 `succeeded` → true；
- 条件未触发的阶段可以 `skipped`，不影响 complete；
- 必需阶段 skipped/failed/pending → false；
- 参与度由 `blind`/`vote` 与 `full_participation` 表达，与 complete 分开。
"""

from __future__ import annotations

from collections.abc import Mapping

from app.core.enums import ALWAYS_REQUIRED_STAGES, STAGE_ORDER, Stage, StageStatus

STAGE_NAMES = tuple(stage.value for stage in STAGE_ORDER)


def required_stages(
    *,
    raw_text: bool,
    kb_covered: bool,
    arbitration_required: bool,
) -> set[str]:
    required = {stage.value for stage in ALWAYS_REQUIRED_STAGES}
    if raw_text:
        required.add(Stage.PREPROCESS.value)
    if kb_covered:
        required.add(Stage.KB_RETRIEVE.value)
    if arbitration_required:
        required.add(Stage.ARBITRATION.value)
    return required


def build_completeness(
    states: Mapping[str, str],
    *,
    raw_text: bool,
    kb_covered: bool,
    arbitration_required: bool,
    blind: str,
    vote: str,
    arbitration: str | None = None,
) -> dict:
    """由各阶段当前状态构造报告 `review_completeness`。"""

    normalized: dict[str, str] = {}
    for stage in STAGE_NAMES:
        status = states.get(stage, StageStatus.PENDING.value)
        if status not in {item.value for item in StageStatus}:
            raise ValueError(f"非法阶段状态: {stage}={status!r}")
        normalized[stage] = status

    required = required_stages(
        raw_text=raw_text, kb_covered=kb_covered, arbitration_required=arbitration_required
    )
    completed = [name for name in STAGE_NAMES if normalized[name] == StageStatus.SUCCEEDED.value]
    skipped = [name for name in STAGE_NAMES if normalized[name] == StageStatus.SKIPPED.value]
    failed = [name for name in STAGE_NAMES if normalized[name] == StageStatus.FAILED.value]
    pending = [
        name
        for name in STAGE_NAMES
        if normalized[name] in (StageStatus.PENDING.value, StageStatus.RUNNING.value)
    ]

    partition = [set(completed), set(skipped), set(failed), set(pending)]
    covered: set[str] = set()
    for group in partition:
        if covered & group:
            raise ValueError(f"阶段状态重叠: {sorted(covered & group)}")
        covered |= group
    if covered != set(STAGE_NAMES):
        raise ValueError(f"阶段未覆盖: {sorted(set(STAGE_NAMES) - covered)}")

    complete = all(normalized[name] == StageStatus.SUCCEEDED.value for name in required)
    full_participation = blind == "3/3" and vote == "3/3"

    return {
        "blind": blind,
        "vote": vote,
        "arbitration": arbitration
        if arbitration is not None
        else (normalized[Stage.ARBITRATION.value] if Stage.ARBITRATION.value in normalized else "pending"),
        "arbitration_required": arbitration_required,
        "stages_completed": completed,
        "stages_skipped": skipped,
        "stages_failed": failed,
        "stages_pending": pending,
        "complete": complete,
        "full_participation": full_participation,
    }
