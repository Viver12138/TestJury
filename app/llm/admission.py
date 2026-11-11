"""生产模型准入门禁（V-01 / Q-09）。

规则：
- 只有 `verification_status=verified` 且 `data_admission_status in {approved, approved_with_masking}`
  的模型角色才能进入生产；
- `approved_with_masking` 还要求显式启用脱敏策略；
- 注册表中的真实模型 ID 必须与准入表一致；
- 准入表缺失、角色缺失、证据为空均拒绝启动，不做“默认放行”。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.llm.registry import ModelRegistry

APPROVED_DATA_STATUS = {"approved", "approved_with_masking"}


class ModelAdmissionError(RuntimeError):
    pass


def load_admission(path: Path) -> dict[str, dict[str, Any]]:
    if not Path(path).exists():
        raise ModelAdmissionError(f"模型准入文件不存在: {path}")
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    roles = payload.get("roles") if isinstance(payload, dict) else None
    if not isinstance(roles, list):
        raise ModelAdmissionError(f"模型准入文件缺少 roles: {path}")
    result: dict[str, dict[str, Any]] = {}
    for item in roles:
        if isinstance(item, dict) and item.get("role"):
            result[str(item["role"])] = item
    return result


def enforce_model_admission(
    registry: ModelRegistry,
    admission_path: Path,
    *,
    roles: tuple[str, ...] = ("chief_blind", "jury_a", "jury_b"),
    masking_enabled: bool = False,
) -> None:
    admission = load_admission(admission_path)
    errors: list[str] = []
    for role in roles:
        entry = admission.get(role)
        if entry is None:
            errors.append(f"{role}: 准入表缺少角色")
            continue
        config = registry.role(role)
        if entry.get("verification_status") != "verified":
            errors.append(f"{role}: verification_status={entry.get('verification_status')!r}")
        data_status = entry.get("data_admission_status")
        if data_status not in APPROVED_DATA_STATUS:
            errors.append(f"{role}: data_admission_status={data_status!r}")
        if data_status == "approved_with_masking" and not masking_enabled:
            errors.append(f"{role}: 需要脱敏但 MASKING_POLICY_ENABLED=false")
        if str(entry.get("real_model_id") or "") != config.model_id:
            errors.append(
                f"{role}: 准入模型 {entry.get('real_model_id')!r} != 注册表 {config.model_id!r}"
            )
        if not entry.get("evidence"):
            errors.append(f"{role}: 缺少准入证据")
    if errors:
        raise ModelAdmissionError("生产模型准入未通过: " + "; ".join(errors))
