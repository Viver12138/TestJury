"""生产模型准入门禁（V-01 / Q-09）。

规则：
- 只有 `verification_status=verified` 且 `data_admission_status in {approved, approved_with_masking}`
  的模型角色才能进入生产；
- `approved_with_masking` 必须有真实 MaskingPolicy、策略 ID 匹配且实际启用；
- 校验 reviewer、DPA、allowed_data_level、evidence 文件存在与哈希；
- 注册表中的真实模型 ID 必须与准入表一致；
- 准入表缺失、角色缺失、证据为空均拒绝启动，不做“默认放行”。
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from app.llm.registry import ModelRegistry

APPROVED_DATA_STATUS = {"approved", "approved_with_masking"}
DATA_LEVELS = {"public", "internal", "sensitive"}


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _allowed_levels(value: Any) -> set[str]:
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    return set()


def _check_dpa(
    entry: dict[str, Any],
    role: str,
    config: Any,
    base: Path,
    request_data_level: str,
    errors: list[str],
) -> None:
    dpa = entry.get("dpa")
    if not isinstance(dpa, dict):
        errors.append(f"{role}: 缺少 DPA 凭据对象")
        return
    document = dpa.get("document")
    digest = dpa.get("sha256")
    if not document or not digest:
        errors.append(f"{role}: DPA 缺少 document/sha256")
        return
    path = Path(str(document))
    resolved = path if path.is_absolute() else (base / path).resolve()
    if not resolved.exists():
        errors.append(f"{role}: DPA 文件不存在 {document}")
    elif _sha256(resolved) != str(digest):
        errors.append(f"{role}: DPA 文件 hash 不匹配")
    if str(dpa.get("supplier") or "") != config.provider:
        errors.append(f"{role}: DPA 供应商与注册表不一致")
    models = dpa.get("models")
    if not isinstance(models, list) or ("*" not in models and config.model_id not in models):
        errors.append(f"{role}: DPA 未覆盖模型 {config.model_id}")
    levels = _allowed_levels(dpa.get("data_levels"))
    if request_data_level not in levels:
        errors.append(f"{role}: DPA 未覆盖数据级别 {request_data_level}")
    signed_at = dpa.get("signed_at")
    expires_at = dpa.get("expires_at")
    try:
        signed = date.fromisoformat(str(signed_at))
        expires = date.fromisoformat(str(expires_at))
    except ValueError:
        errors.append(f"{role}: DPA signed_at/expires_at 不是 ISO 日期")
        return
    today = datetime.now(UTC).date()
    if signed > today:
        errors.append(f"{role}: DPA 签署日期在未来")
    if expires < today:
        errors.append(f"{role}: DPA 已过期")


def _check_evidence(
    entry: dict[str, Any], role: str, base: Path, errors: list[str]
) -> None:
    evidence = entry.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append(f"{role}: 缺少准入证据")
        return
    hashes = entry.get("evidence_hashes")
    if not isinstance(hashes, dict):
        errors.append(f"{role}: 缺少 evidence_hashes（无法校验证据完整性）")
        return
    for item in evidence:
        path = Path(str(item))
        resolved = path if path.is_absolute() else (base / path).resolve()
        if not resolved.exists():
            errors.append(f"{role}: 证据文件不存在 {item}")
            continue
        expected = hashes.get(str(item))
        if not expected:
            errors.append(f"{role}: 证据缺少 hash {item}")
        elif str(expected) != _sha256(resolved):
            errors.append(f"{role}: 证据 hash 不匹配 {item}")


def enforce_model_admission(
    registry: ModelRegistry,
    admission_path: Path,
    *,
    roles: tuple[str, ...] = ("chief_blind", "jury_a", "jury_b"),
    masking_enabled: bool = False,
    masking_policy_id: str | None = None,
    request_data_level: str = "internal",
) -> None:
    admission = load_admission(admission_path)
    if request_data_level not in DATA_LEVELS:
        raise ModelAdmissionError(f"非法数据级别: {request_data_level!r}")
    base = Path(admission_path).resolve().parent.parent
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
        if str(entry.get("real_model_id") or "") != config.model_id:
            errors.append(
                f"{role}: 准入模型 {entry.get('real_model_id')!r} != 注册表 {config.model_id!r}"
            )
        if not str(entry.get("reviewer") or "").strip():
            errors.append(f"{role}: reviewer 未填写")
        if entry.get("dpa_signed") is not True:
            errors.append(f"{role}: DPA 未签署")
        _check_dpa(entry, role, config, base, request_data_level, errors)
        allowed = _allowed_levels(entry.get("allowed_data_level"))
        if not allowed:
            errors.append(f"{role}: allowed_data_level 未定义")
        elif request_data_level not in allowed:
            errors.append(
                f"{role}: 数据级别 {request_data_level!r} 不在允许范围 {sorted(allowed)}"
            )
        requires_masking = bool(entry.get("requires_masking"))
        allow_raw = bool(entry.get("allow_raw_case"))
        if data_status == "approved_with_masking":
            if not requires_masking:
                errors.append(f"{role}: approved_with_masking 必须 requires_masking=true")
            if allow_raw:
                errors.append(f"{role}: approved_with_masking 不得 allow_raw_case=true")
            if not masking_enabled:
                errors.append(f"{role}: 需要脱敏但 MASKING_POLICY_ENABLED=false")
            if not masking_policy_id:
                errors.append(f"{role}: 未配置 MaskingPolicy")
            entry_policy = str(entry.get("masking_policy_id") or "")
            if entry_policy != str(masking_policy_id or ""):
                errors.append(
                    f"{role}: 准入脱敏策略 {entry_policy!r} != 实际 {masking_policy_id!r}"
                )
        elif data_status == "approved":
            if requires_masking:
                errors.append(f"{role}: requires_masking=true 但数据准入未批准脱敏")
            if not allow_raw:
                errors.append(f"{role}: approved 但 allow_raw_case=false 且无脱敏策略")
        _check_evidence(entry, role, base, errors)
    if errors:
        raise ModelAdmissionError("生产模型准入未通过: " + "; ".join(errors))

