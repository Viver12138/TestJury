"""Rubric 加载与校验：`rubric/rubric.yaml` 是机器可执行事实源（docs/04 §9）。

M0 要求（ACC-M0-009/010）：
- 加载 + JSON Schema 校验 + 业务约束校验；
- 生产模式拒绝 `draft`；
- 当前版本必须能找到冻结副本 `rubric/versions/v<version>.yaml`，历史报告按当时版本读取；
- 校验失败必须给出字段/路径，禁止只报"校验失败"。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from app.core.enums import EvidenceStatus, Severity, VoteValidity


class RubricError(Exception):
    """Rubric 无法加载或校验失败。"""

    def __init__(self, message: str, issues: list[str] | None = None) -> None:
        self.issues = issues or []
        detail = message if not self.issues else f"{message}: " + "; ".join(self.issues)
        super().__init__(detail)


@dataclass(frozen=True)
class Rubric:
    version: str
    status: str
    data: dict[str, Any]
    source_path: Path

    @property
    def is_published(self) -> bool:
        return self.status == "published"

    @property
    def checkpoint_ids(self) -> set[str]:
        return {
            checkpoint["id"]
            for spec in self.data.get("dimensions", {}).values()
            for checkpoint in spec.get("checkpoints", [])
        }

    @property
    def categories(self) -> dict[str, dict[str, Any]]:
        return dict(self.data.get("categories", {}))

    def severity_for(self, category: str) -> dict[str, str]:
        return dict(self.data.get("severity", {}))

    def category_dimensions(self) -> dict[str, list[str]]:
        return {
            name: list(spec.get("dimensions", []))
            for name, spec in self.data.get("categories", {}).items()
        }


def _schema_issues(data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema)
    issues: list[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
        path = "/".join(str(part) for part in error.absolute_path) or "<root>"
        issues.append(f"{path}: {error.message}")
    return issues


def _business_issues(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []

    version = str(data.get("version", ""))
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        issues.append(f"version: 必须是 SemVer X.Y.Z，实际 {version!r}")
    if data.get("status") not in ("draft", "reviewed", "published", "deprecated"):
        issues.append(f"status: 非法状态 {data.get('status')!r}")

    dimensions = data.get("dimensions", {})
    seen: dict[str, str] = {}
    for dimension, spec in dimensions.items():
        checkpoints = spec.get("checkpoints", [])
        if not checkpoints:
            issues.append(f"dimensions.{dimension}.checkpoints: 不能为空")
        for checkpoint in checkpoints:
            cid = checkpoint.get("id")
            if not cid:
                issues.append(f"dimensions.{dimension}.checkpoints: 检查点缺少 id")
                continue
            if cid in seen:
                issues.append(f"checkpoint {cid}: ID 重复（{seen[cid]} 与 {dimension}）")
            seen[cid] = dimension

    categories = data.get("categories", {})
    if not categories:
        issues.append("categories: 不能为空")
    for name, spec in categories.items():
        refs = spec.get("dimensions", [])
        if not refs:
            issues.append(f"categories.{name}.dimensions: 不能为空")
        for dimension in refs:
            if dimension not in dimensions:
                issues.append(f"categories.{name}: 引用未定义维度 {dimension!r}")

    fusion = data.get("fusion", {})
    suspect = fusion.get("cosine_suspect")
    high = fusion.get("cosine_high")
    if not isinstance(suspect, (int, float)) or not isinstance(high, (int, float)):
        issues.append("fusion: cosine_suspect/cosine_high 必须是数值")
    elif not (0 <= suspect < high <= 1):
        issues.append(
            f"fusion: 必须满足 0 ≤ cosine_suspect({suspect}) < cosine_high({high}) ≤ 1"
        )

    voting = data.get("voting", {})
    if voting.get("min_valid_votes_per_candidate") != 2:
        issues.append(
            "voting.min_valid_votes_per_candidate: 必须与 docs/12 §6 的 2 票一致，"
            f"实际 {voting.get('min_valid_votes_per_candidate')!r}"
        )
    if voting.get("severity_gap_for_human") != 2:
        issues.append(
            "voting.severity_gap_for_human: 必须与 docs/12 §3 的跨两级一致，"
            f"实际 {voting.get('severity_gap_for_human')!r}"
        )

    validity_states = set(voting.get("validity_states", []))
    if validity_states != {item.value for item in VoteValidity}:
        issues.append(
            "voting.validity_states: 与 docs/17 issue_votes.validity 不一致，"
            f"缺 {sorted({item.value for item in VoteValidity} - validity_states)}，"
            f"多 {sorted(validity_states - {item.value for item in VoteValidity})}"
        )

    severity_states = set(data.get("severity", {}))
    if severity_states != {item.value for item in Severity}:
        issues.append(
            f"severity: 与 docs/17 issues.severity 不一致，实际 {sorted(severity_states)}"
        )

    evidence_status = set(data.get("evidence", {}).get("status", []))
    if evidence_status != {item.value for item in EvidenceStatus}:
        issues.append(
            f"evidence.status: 与 docs/17 evidence_status 不一致，实际 {sorted(evidence_status)}"
        )

    claim = data.get("evidence", {}).get("claim", {})
    if claim.get("allow_empty_core") is not False:
        issues.append("evidence.claim.allow_empty_core: 必须为 false（docs/12 §4.1 要求 core claim）")

    rules = data.get("conclusion_rules", {})
    if rules.get("auto_pass") is not False:
        issues.append("conclusion_rules.auto_pass: 必须为 false（系统永不自动通过）")

    return issues


@dataclass
class RubricRepository:
    rubric_path: Path
    schema_path: Path
    versions_dir: Path | None = None
    _schema: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.rubric_path = Path(self.rubric_path)
        self.schema_path = Path(self.schema_path)
        self.versions_dir = Path(self.versions_dir) if self.versions_dir else self.rubric_path.parent / "versions"

    def _load_schema(self) -> dict[str, Any]:
        if self._schema is None:
            try:
                self._schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
            except FileNotFoundError as exc:
                raise RubricError(f"Rubric Schema 不存在: {self.schema_path}") from exc
            except json.JSONDecodeError as exc:
                raise RubricError(f"Rubric Schema 不是合法 JSON: {self.schema_path}: {exc}") from exc
        return self._schema

    def load_active(self, *, require_published: bool = False) -> Rubric:
        try:
            raw = yaml.safe_load(self.rubric_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RubricError(f"Rubric 不存在: {self.rubric_path}") from exc
        except yaml.YAMLError as exc:
            raise RubricError(f"Rubric 不是合法 YAML: {self.rubric_path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise RubricError(f"{self.rubric_path}: 顶层必须是对象")

        issues = _schema_issues(raw, self._load_schema())
        issues.extend(_business_issues(raw))
        if issues:
            raise RubricError("Rubric 校验失败", issues)

        version = str(raw["version"])
        copy_path = self.versions_dir / f"v{version}.yaml"
        if not copy_path.exists():
            raise RubricError(f"缺少当前版本的冻结副本: {copy_path}")
        try:
            frozen = yaml.safe_load(copy_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise RubricError(f"冻结副本不是合法 YAML: {copy_path}: {exc}") from exc
        if frozen != raw:
            raise RubricError(
                f"冻结副本与 rubric.yaml 内容不一致（改规则必须递增版本）: {copy_path}"
            )

        status = str(raw["status"])
        if require_published and status != "published":
            raise RubricError(
                f"Rubric 状态为 {status!r}，生产模式只接受 published（docs/08 §7、rubric/README）"
            )

        return Rubric(version=version, status=status, data=raw, source_path=self.rubric_path)

    def load_version(self, version: str) -> Rubric:
        """按历史版本加载冻结副本，避免用新版本覆盖旧报告（ACC-M0-010）。"""

        copy_path = self.versions_dir / f"v{version}.yaml"
        if not copy_path.exists():
            raise RubricError(f"不存在的 Rubric 版本: {version}（缺少 {copy_path}）")
        try:
            raw = yaml.safe_load(copy_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise RubricError(f"冻结副本不是合法 YAML: {copy_path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise RubricError(f"{copy_path}: 顶层必须是对象")
        if str(raw.get("version")) != version:
            raise RubricError(
                f"冻结副本版本不匹配: 期望 {version}，文件内为 {raw.get('version')!r}"
            )
        return Rubric(version=version, status=str(raw.get("status")), data=raw, source_path=copy_path)
