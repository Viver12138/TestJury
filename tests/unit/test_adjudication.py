"""人工裁决工作台的数据校验与写入（不产生 AI 代替人工的标签）。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.adjudication import (
    AdjudicationError,
    append_history,
    export_csv,
    load_case,
    record_decision,
    save_case,
    set_case_verdict,
    stats,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ADJ_ROOT = REPO_ROOT / "data" / "projects" / "testlab-arcade" / "adjudication"


def test_all_candidates_start_pending() -> None:
    files = sorted(ADJ_ROOT.glob("*.yaml"))
    assert len(files) >= 8
    for path in files:
        data = load_case(path)
        assert data["candidates"]
        for candidate in data["candidates"]:
            assert candidate["final"]["validity"] == "pending"
            assert candidate["final"]["adjudicator"] is None
        assert data["case_level"]["verdict"] == "pending"


def test_record_decision_and_history(workdir: Path) -> None:
    target = workdir / "adjudication"
    target.mkdir()
    shutil.copy2(ADJ_ROOT / "UI-GAME-007.yaml", target / "UI-GAME-007.yaml")
    path = target / "UI-GAME-007.yaml"
    data = load_case(path)

    entry = record_decision(
        data,
        "CAND-UI-GAME-007-01",
        validity="valid",
        severity="blocker",
        category="状态不自洽",
        correction="拆分为启动中/保存中两条用例",
        adjudicator="reviewer-1",
        at="2026-11-11T12:00:00+08:00",
    )
    save_case(path, data)
    append_history(target / "history.jsonl", entry)

    reloaded = load_case(path)
    final = reloaded["candidates"][0]["final"]
    assert final["validity"] == "valid"
    assert final["severity"] == "blocker"
    assert final["adjudicator"] == "reviewer-1"
    assert (target / "history.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_invalid_decisions_are_rejected(workdir: Path) -> None:
    target = workdir / "UI-GAME-007.yaml"
    shutil.copy2(ADJ_ROOT / "UI-GAME-007.yaml", target)
    data = load_case(target)

    with pytest.raises(AdjudicationError):
        record_decision(
            data,
            "CAND-UI-GAME-007-01",
            validity="valid",
            severity=None,
            category="状态不自洽",
            adjudicator="reviewer-1",
        )
    with pytest.raises(AdjudicationError):
        record_decision(
            data,
            "CAND-UI-GAME-007-01",
            validity="invalid",
            severity="blocker",
            category=None,
            adjudicator="reviewer-1",
        )
    with pytest.raises(AdjudicationError):
        record_decision(
            data,
            "CAND-UI-GAME-007-01",
            validity="invalid",
            adjudicator="",
        )
    with pytest.raises(AdjudicationError):
        record_decision(data, "CAND-NOT-FOUND", validity="invalid", adjudicator="reviewer-1")


def test_case_verdict_and_stats(workdir: Path) -> None:
    target = workdir / "adjudication"
    target.mkdir()
    shutil.copy2(ADJ_ROOT / "UI-GAME-007.yaml", target / "UI-GAME-007.yaml")
    path = target / "UI-GAME-007.yaml"
    data = load_case(path)
    record_decision(
        data,
        "CAND-UI-GAME-007-01",
        validity="valid",
        severity="blocker",
        category="状态不自洽",
        adjudicator="reviewer-1",
    )
    record_decision(
        data,
        "CAND-UI-GAME-007-02",
        validity="invalid",
        adjudicator="reviewer-1",
    )
    set_case_verdict(data, verdict="needs_fix", defect_count=1, adjudicator="reviewer-1")
    save_case(path, data)

    result = stats(target)
    assert result["cases"] == 1
    assert result["decided"] == 2
    assert result["valid"] == 1
    assert result["invalid"] == 1
    assert result["cases_done"] == 1


def test_export_csv(workdir: Path) -> None:
    target = workdir / "adjudication"
    target.mkdir()
    shutil.copy2(ADJ_ROOT / "UI-GAME-007.yaml", target / "UI-GAME-007.yaml")
    rows = export_csv(target, target / "out.csv")
    assert rows == 6
    assert (target / "out.csv").read_text(encoding="utf-8-sig").startswith("case_id,case_title,candidate_id")
