"""报告 Schema 加载与校验（`schemas/report.schema.json` 为唯一结构）。

- 按 `report_schema_version` 选择 Schema，未知版本拒绝加载，不按最新版强转（docs/14 §7）。
- 校验错误必须给出字段路径，便于定位（ACC-M0-007）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

REPORT_SCHEMA_VERSION = "report-1.0"

# version -> (当前 Schema 文件, 冻结副本文件, $id)
SUPPORTED_SCHEMAS: dict[str, tuple[str, str, str]] = {
    "report-1.0": (
        "report.schema.json",
        "report-1.0.schema.json",
        "https://testjury.local/schemas/report.schema.json",
    ),
}


class ReportSchemaError(Exception):
    pass


class UnsupportedReportVersion(ReportSchemaError):
    def __init__(self, version: str) -> None:
        self.version = version
        super().__init__(
            f"不支持的 report_schema_version: {version!r}；"
            f"已知版本 {sorted(SUPPORTED_SCHEMAS)}（历史报告按版本读取，不自动迁移）"
        )


class ReportValidationError(ReportSchemaError):
    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("报告不符合 Schema: " + "; ".join(issues))


@dataclass(frozen=True)
class ReportSchema:
    version: str
    schema: dict[str, Any]
    path: Path

    def validate(self, report: dict[str, Any]) -> None:
        validator = jsonschema.Draft202012Validator(self.schema)
        issues: list[str] = []
        for error in sorted(validator.iter_errors(report), key=lambda item: list(item.absolute_path)):
            path = "/".join(str(part) for part in error.absolute_path) or "<root>"
            issues.append(f"{path}: {error.message}")
        if issues:
            raise ReportValidationError(issues)


def load_report_schema(
    version: str,
    *,
    schema_dir: Path | None = None,
) -> ReportSchema:
    if version not in SUPPORTED_SCHEMAS:
        raise UnsupportedReportVersion(version)
    filename, _, expected_id = SUPPORTED_SCHEMAS[version]
    base = Path(schema_dir) if schema_dir else Path(__file__).resolve().parents[2] / "schemas"
    path = base / filename
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReportSchemaError(f"报告 Schema 不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReportSchemaError(f"报告 Schema 不是合法 JSON: {path}: {exc}") from exc
    actual_id = schema.get("$id")
    if actual_id != expected_id:
        raise ReportSchemaError(
            f"{path}: $id 应为 {expected_id!r}，实际 {actual_id!r}（版本与文件必须一一对应）"
        )
    return ReportSchema(version=version, schema=schema, path=path)


def verify_frozen_copy(version: str, *, schema_dir: Path | None = None) -> None:
    """校验当前 Schema 与 `schemas/versions/` 冻结副本字节一致。"""

    if version not in SUPPORTED_SCHEMAS:
        raise UnsupportedReportVersion(version)
    filename, frozen_name, _ = SUPPORTED_SCHEMAS[version]
    base = Path(schema_dir) if schema_dir else Path(__file__).resolve().parents[2] / "schemas"
    active = base / filename
    frozen = base / "versions" / frozen_name
    if not frozen.exists():
        raise ReportSchemaError(f"缺少冻结副本: {frozen}")
    active_digest = hashlib.sha256(active.read_bytes()).hexdigest()
    frozen_digest = hashlib.sha256(frozen.read_bytes()).hexdigest()
    if active_digest != frozen_digest:
        raise ReportSchemaError(
            f"冻结副本被改动: {frozen}（sha256 {frozen_digest[:12]}）"
            f" 与 {active}（sha256 {active_digest[:12]}）不一致"
        )
