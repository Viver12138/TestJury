"""项目数据入口契约：functional 评审只能读 57 条功能用例。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT = REPO_ROOT / "data" / "projects" / "testlab-arcade"


def _load(name: str):
    return json.loads((PROJECT / name).read_text(encoding="utf-8"))


def test_project_review_payloads_point_to_functional_only() -> None:
    project = yaml.safe_load((PROJECT / "project.yaml").read_text(encoding="utf-8"))
    assert project["normalized"]["review_payloads"] == "functional_case_payloads.json"
    assert project["normalized"]["legacy_unclassified_review_payloads"] == "case_payloads.json"

    payloads = _load("functional_case_payloads.json")
    assert len(payloads) == 57
    assert project["review_payloads_count"] == 57
    for item in payloads:
        case = item["case"]
        assert case["test_type"] == "functional"
        assert not case["case_id"].startswith("UI-")


def test_legacy_ui_payloads_are_not_functional_entry() -> None:
    legacy = _load("case_payloads.json")
    assert len(legacy) == 55
    assert all(item["case"]["case_id"].startswith("UI-") for item in legacy)


def test_functional_modules_match_payloads() -> None:
    project = yaml.safe_load((PROJECT / "project.yaml").read_text(encoding="utf-8"))
    cases = _load("functional_cases_v1.1.json")
    counts = Counter(case["module"] for case in cases)
    assert dict(counts) == project["functional_modules"]
    assert len(cases) == 62
    assert sum(1 for case in cases if case["case_type"] == "non_functional") == 5
