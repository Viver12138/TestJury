"""ACC-M0-007：报告 Schema 加载、校验与版本识别（docs/14 §7）。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from app.schemas.report import (
    REPORT_SCHEMA_VERSION,
    ReportValidationError,
    UnsupportedReportVersion,
    load_report_schema,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _valid_report() -> dict:
    return {
        "review_id": "8f1c0d2e",
        "case_id": "TC-DIG-0012",
        "case_version": 1,
        "test_type": "functional",
        "test_type_source": "request",
        "generation": 1,
        "parent_review_id": None,
        "status": "done",
        "stage": "render",
        "ai_verdict": "conditional",
        "human_status": "pending",
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "degraded": False,
        "degraded_reasons": [],
        "participants": ["chief:mock", "jury_a:mock", "jury_b:mock"],
        "topology": "multi",
        "review_completeness": {
            "blind": "3/3",
            "vote": "3/3",
            "arbitration": "skipped",
            "arbitration_required": False,
            "stages_completed": ["input_check", "blind_review"],
            "stages_skipped": ["arbitration"],
            "stages_failed": [],
            "stages_pending": [],
            "complete": True,
            "full_participation": True,
        },
        "input_quality": {"hard_errors": [], "soft_issues": []},
        "versions": {
            "kb": "kb-test",
            "rubric": "0.2.0",
            "prompts": {"chief_blind": "p-1a2b"},
            "model_config": "models-test",
        },
        "summary": {
            "total_issues": 1,
            "blocker": 0,
            "major": 1,
            "suggestion": 0,
        },
        "issues": [
            {
                "issue_no": 1,
                "candidate_id": "c-001",
                "step_index": 3,
                "dimension": "test_design",
                "severity": "major",
                "category": "预期不明确",
                "evidence_quote": "点击【发现】按钮",
                "rationale": "未说明判定条件",
                "suggestion": "补充判定条件",
                "status": "adopted",
                "votes": {
                    "chief_blind": {"validity": "accept", "severity": "major"},
                    "jury_a": {"validity": "accept", "severity": "major"},
                    "jury_b": {"validity": "accept", "severity": "suggestion"},
                },
                "vote_summary": {
                    "support": 3,
                    "reject": 0,
                    "not_assessed": 0,
                    "uncertain": 0,
                    "support_ratio": 1.0,
                    "severity_distribution": {"blocker": 0, "major": 2, "suggestion": 1},
                    "severity_disputed": False,
                    "vote_completeness": "3/3",
                },
                "evidence_status": "grounded",
            }
        ],
        "human_review_items": [],
        "kb_gaps": [],
        "decision_summary": {"human_status": "pending", "latest_decision": None, "history_count": 0},
        "created_at": "2026-11-10T10:00:00+08:00",
        "finished_at": "2026-11-10T10:01:00+08:00",
    }


def test_schema_file_is_valid_json_schema() -> None:
    schema = load_report_schema(REPORT_SCHEMA_VERSION, schema_dir=REPO_ROOT / "schemas")
    jsonschema.Draft202012Validator.check_schema(schema.schema)


def test_valid_report_passes() -> None:
    schema = load_report_schema(REPORT_SCHEMA_VERSION, schema_dir=REPO_ROOT / "schemas")
    schema.validate(_valid_report())


def test_missing_required_section_is_rejected_with_path() -> None:
    schema = load_report_schema(REPORT_SCHEMA_VERSION, schema_dir=REPO_ROOT / "schemas")
    report = _valid_report()
    del report["versions"]
    with pytest.raises(ReportValidationError) as excinfo:
        schema.validate(report)
    assert any("versions" in issue for issue in excinfo.value.issues), excinfo.value.issues


def test_unknown_schema_version_is_not_coerced() -> None:
    with pytest.raises(UnsupportedReportVersion) as excinfo:
        load_report_schema("report-9.9", schema_dir=REPO_ROOT / "schemas")
    assert "report-9.9" in str(excinfo.value)


def test_issue_field_path_is_reported() -> None:
    schema = load_report_schema(REPORT_SCHEMA_VERSION, schema_dir=REPO_ROOT / "schemas")
    report = copy.deepcopy(_valid_report())
    report["issues"][0]["severity"] = "catastrophic"
    with pytest.raises(ReportValidationError) as excinfo:
        schema.validate(report)
    assert any("issues/0/severity" in issue for issue in excinfo.value.issues), excinfo.value.issues


def test_schema_id_matches_registered_version() -> None:
    schema = load_report_schema(REPORT_SCHEMA_VERSION, schema_dir=REPO_ROOT / "schemas")
    payload: dict = json.loads((REPO_ROOT / "schemas" / "report.schema.json").read_text("utf-8"))
    assert payload["$id"] == "https://testjury.local/schemas/report.schema.json"
    assert schema.version == REPORT_SCHEMA_VERSION
