"""模型输出五层校验与信任边界（docs/06 §3.1、§3.7；docs/12 §8）。

M0 先实现可测的纯函数部分：
- 丢弃模型输出中的决策/状态/权限字段（`ai_verdict` / `human_status` / `status` / 角色等）；
- 校验枚举、引用与数值范围，失败返回结构化问题而不是静默修补；
- 解析失败不猜测，交由调用方按角色失败处理。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.core.enums import Severity, VoteValidity

# 模型永远不能写这些字段：出现即丢弃并记 parse_warning（ACC-M0-013）。
FORBIDDEN_MODEL_FIELDS: frozenset[str] = frozenset(
    {
        "ai_verdict",
        "human_status",
        "human_decision",
        "decision",
        "approved",
        "permissions",
        "role",
        "roles",
        "status",
    }
)


@dataclass
class SanitizedOutput:
    data: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationIssue:
    field: str
    message: str


def sanitize_model_output(payload: Any, *, prefix: str = "") -> SanitizedOutput:
    """递归删除模型输出中的决策/权限字段，保留其余结构。"""

    warnings: list[str] = []

    def _clean(value: Any, path: str) -> Any:
        if isinstance(value, Mapping):
            cleaned: dict[str, Any] = {}
            for key, item in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if key in FORBIDDEN_MODEL_FIELDS:
                    warnings.append(f"dropped_model_field:{child_path}")
                    continue
                cleaned[key] = _clean(item, child_path)
            return cleaned
        if isinstance(value, list):
            return [_clean(item, f"{path}[{index}]") for index, item in enumerate(value)]
        return value

    if not isinstance(payload, Mapping):
        return SanitizedOutput(data={}, warnings=[f"non_object_output:{prefix or 'root'}"])
    return SanitizedOutput(data=_clean(payload, prefix), warnings=warnings)


def validate_issue_payload(
    issue: Mapping[str, Any],
    *,
    allowed_evidence_refs: Iterable[str] | None = None,
    label: str = "issue",
) -> list[ValidationIssue]:
    """校验单条模型提出问题的枚举、数值与引用；不做自动修正。"""

    issues: list[ValidationIssue] = []
    if not issue.get("rationale"):
        issues.append(ValidationIssue(f"{label}.rationale", "理由不能为空"))

    severity = issue.get("severity")
    if severity is not None and severity not in {item.value for item in Severity}:
        issues.append(ValidationIssue(f"{label}.severity", f"非法严重级 {severity!r}"))

    validity = issue.get("validity")
    if validity is not None and validity not in {item.value for item in VoteValidity}:
        issues.append(ValidationIssue(f"{label}.validity", f"非法成立性 {validity!r}"))

    confidence = issue.get("model_confidence")
    if confidence is not None and not (isinstance(confidence, (int, float)) and 0 <= confidence <= 1):
        issues.append(ValidationIssue(f"{label}.model_confidence", "必须在 0..1"))

    if allowed_evidence_refs is not None:
        allowed = set(allowed_evidence_refs)
        refs = issue.get("evidence_refs") or []
        if not isinstance(refs, list):
            issues.append(ValidationIssue(f"{label}.evidence_refs", "必须是数组"))
        else:
            for index, ref in enumerate(refs):
                ref_id = ref.get("ref") if isinstance(ref, Mapping) else ref
                if ref_id is None:
                    issues.append(ValidationIssue(f"{label}.evidence_refs[{index}]", "缺少 ref"))
                elif ref_id not in allowed:
                    issues.append(
                        ValidationIssue(
                            f"{label}.evidence_refs[{index}].ref",
                            f"引用了证据包中不存在的条目: {ref_id}",
                        )
                    )
    return issues
