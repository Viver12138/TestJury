"""ACC-M0-008：报告 Schema 与 `schemas/versions/` 冻结副本字节一致。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.schemas.report import (
    REPORT_SCHEMA_VERSION,
    SUPPORTED_SCHEMAS,
    ReportSchemaError,
    load_report_schema,
    verify_frozen_copy,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "schemas"


def test_frozen_copy_matches_active_schema() -> None:
    verify_frozen_copy(REPORT_SCHEMA_VERSION, schema_dir=SCHEMA_DIR)

    filename, frozen_name, _ = SUPPORTED_SCHEMAS[REPORT_SCHEMA_VERSION]
    active = SCHEMA_DIR / filename
    frozen = SCHEMA_DIR / "versions" / frozen_name
    assert hashlib.sha256(active.read_bytes()).hexdigest() == hashlib.sha256(
        frozen.read_bytes()
    ).hexdigest()


def test_frozen_copy_missing_is_reported(workdir: Path) -> None:
    schema_dir = workdir / "schemas"
    (schema_dir / "versions").mkdir(parents=True)
    source = SCHEMA_DIR / "report.schema.json"
    (schema_dir / "report.schema.json").write_bytes(source.read_bytes())
    (schema_dir / "versions" / "report-1.0.schema.json").unlink(missing_ok=True)

    with pytest.raises(ReportSchemaError) as excinfo:
        verify_frozen_copy(REPORT_SCHEMA_VERSION, schema_dir=schema_dir)
    assert "冻结副本" in str(excinfo.value)


def test_frozen_copy_drift_is_reported(workdir: Path) -> None:
    schema_dir = workdir / "schemas"
    (schema_dir / "versions").mkdir(parents=True)
    source = SCHEMA_DIR / "report.schema.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["title"] = "Tampered"
    (schema_dir / "report.schema.json").write_text(json.dumps(payload), encoding="utf-8")
    (schema_dir / "versions" / "report-1.0.schema.json").write_bytes(source.read_bytes())

    with pytest.raises(ReportSchemaError) as excinfo:
        verify_frozen_copy(REPORT_SCHEMA_VERSION, schema_dir=schema_dir)
    assert "不一致" in str(excinfo.value)


def test_schema_id_and_version_are_one_to_one() -> None:
    schema = load_report_schema(REPORT_SCHEMA_VERSION, schema_dir=SCHEMA_DIR)
    assert schema.schema["$id"] == SUPPORTED_SCHEMAS[REPORT_SCHEMA_VERSION][2]

