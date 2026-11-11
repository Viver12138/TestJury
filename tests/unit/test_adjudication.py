"""人工裁决工作台的数据校验与写入（不产生 AI 代替人工的标签）。"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.adjudication import (
    AdjudicationError,
    append_history,
    case_snapshot,
    export_csv,
    import_decisions_from_csv,
    load_case,
    record_decision,
    recover_imports,
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


def test_import_is_blocked_by_concurrent_lock(workdir: Path) -> None:
    target = workdir / "adjudication"
    target.mkdir()
    shutil.copy2(ADJ_ROOT / "UI-GAME-007.yaml", target / "UI-GAME-007.yaml")
    csv_path = target / "adjudication.csv"
    export_csv(target, csv_path)
    (target / ".imports").mkdir()
    (target / ".imports" / "import.lock").write_text("held", encoding="utf-8")
    with pytest.raises(AdjudicationError, match="另一个裁决导入"):
        import_decisions_from_csv(target, csv_path)


def test_recover_imports_restores_backup(workdir: Path) -> None:
    target = workdir / "adjudication"
    target.mkdir()
    path = target / "UI-GAME-007.yaml"
    shutil.copy2(ADJ_ROOT / "UI-GAME-007.yaml", path)
    original = path.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    imports = target / ".imports"
    backup_dir = imports / "batch1.backup"
    backup_dir.mkdir(parents=True)
    shutil.copy2(path, backup_dir / path.name)
    path.write_text("changed", encoding="utf-8")
    (imports / "batch1.json").write_text(
        json.dumps(
            {
                "batch_id": "batch1",
                "status": "applying",
                "files": [
                    {
                        "case_id": "UI-GAME-007",
                        "path": path.name,
                        "before_hash": digest,
                        "backup_hash": digest,
                    }
                ],
                "history_existed": False,
            }
        ),
        encoding="utf-8",
    )
    result = recover_imports(target)
    assert result["recovered"] == 1
    assert path.read_bytes() == original
    journal = json.loads((imports / "batch1.json").read_text(encoding="utf-8"))
    assert journal["status"] == "recovered"


def test_recover_imports_rejects_missing_backup(workdir: Path) -> None:
    target = workdir / "adjudication"
    target.mkdir()
    imports = target / ".imports"
    imports.mkdir()
    (imports / "batch2.json").write_text(
        json.dumps(
            {
                "batch_id": "batch2",
                "status": "applying",
                "files": [
                    {
                        "case_id": "UI-GAME-007",
                        "path": "UI-GAME-007.yaml",
                        "before_hash": "x",
                        "backup_hash": "x",
                    }
                ],
                "history_existed": False,
            }
        ),
        encoding="utf-8",
    )
    result = recover_imports(target)
    assert result["recovered"] == 0
    assert result["failed"] == 1
    journal = json.loads((imports / "batch2.json").read_text(encoding="utf-8"))
    assert journal["status"] == "recovery_failed"


def test_case_snapshot_formats_functional_steps() -> None:
    snapshot = case_snapshot(
        {
            "module": "登录",
            "priority": "P0",
            "requirement_ref": "策划案5.1",
            "preconditions": ["未登录"],
            "steps": [
                {"index": 1, "action": "点击登录", "expected": "进入主界面"},
                {"index": 2, "action": "刷新", "expected": "保持登录"},
            ],
        }
    )
    assert snapshot["ui_spec_ref"] == "策划案5.1"
    assert "1. 点击登录 => 进入主界面" in snapshot["steps"]
    assert "进入主界面" in snapshot["expected"]


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
    # 还有 pending 时不能填最终结论
    with pytest.raises(AdjudicationError, match="未裁决"):
        set_case_verdict(data, verdict="needs_fix", defect_count=1, adjudicator="reviewer-1")
    for candidate in data["candidates"][2:]:
        record_decision(
            data,
            candidate["candidate_id"],
            validity="invalid",
            adjudicator="reviewer-1",
        )
    set_case_verdict(data, verdict="needs_fix", defect_count=1, adjudicator="reviewer-1")
    save_case(path, data)

    result = stats(target)
    assert result["cases"] == 1
    assert result["decided"] == 6
    assert result["valid"] == 1
    assert result["invalid"] == 5
    assert result["cases_done"] == 1


def test_export_csv(workdir: Path) -> None:
    target = workdir / "adjudication"
    target.mkdir()
    shutil.copy2(ADJ_ROOT / "UI-GAME-007.yaml", target / "UI-GAME-007.yaml")
    rows = export_csv(target, target / "out.csv")
    assert rows == 6
    assert (target / "out.csv").read_text(encoding="utf-8-sig").startswith("case_id,case_title,candidate_id")


def test_import_csv_merges_decisions(workdir: Path) -> None:
    target = workdir / "adjudication"
    target.mkdir()
    shutil.copy2(ADJ_ROOT / "UI-GAME-007.yaml", target / "UI-GAME-007.yaml")
    csv_path = target / "adjudication.csv"
    export_csv(target, csv_path)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0].update(
        {
            "final_validity": "valid",
            "final_severity": "blocker",
            "final_category": "状态不自洽",
            "correction": "拆分为启动中/保存中两条用例",
            "adjudicator": "reviewer-1",
            "adjudicated_at": "2026-11-11T12:00:00+08:00",
            "case_verdict": "needs_fix",
            "case_defect_count": "1",
            "case_note": "拆分后重跑",
        }
    )
    for row in rows[1:]:
        row.update({"final_validity": "invalid", "adjudicator": "reviewer-1"})
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    result = import_decisions_from_csv(target, csv_path)
    assert result["decisions"] == 6
    data = load_case(target / "UI-GAME-007.yaml")
    final = data["candidates"][0]["final"]
    assert final["validity"] == "valid"
    assert final["adjudicator"] == "reviewer-1"
    assert data["case_level"]["verdict"] == "needs_fix"
    assert data["case_level"]["defect_count"] == 1
    assert (target / "history.jsonl").exists()


def test_import_csv_dry_run_does_not_write(workdir: Path) -> None:
    target = workdir / "adjudication"
    target.mkdir()
    shutil.copy2(ADJ_ROOT / "UI-GAME-007.yaml", target / "UI-GAME-007.yaml")
    csv_path = target / "adjudication.csv"
    export_csv(target, csv_path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0].update(
        {"final_validity": "valid", "final_severity": "major", "final_category": "预期不明确", "adjudicator": "reviewer-1"}
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    result = import_decisions_from_csv(target, csv_path, dry_run=True)
    assert result["dry_run"] is True
    assert load_case(target / "UI-GAME-007.yaml")["candidates"][0]["final"]["validity"] == "pending"


def test_import_csv_rejects_path_traversal(workdir: Path) -> None:
    target = workdir / "adjudication"
    target.mkdir()
    shutil.copy2(ADJ_ROOT / "UI-GAME-007.yaml", target / "UI-GAME-007.yaml")
    csv_path = target / "adjudication.csv"
    export_csv(target, csv_path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0].update({"case_id": "../evil", "final_validity": "invalid", "adjudicator": "reviewer-1"})
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(AdjudicationError, match="case_id"):
        import_decisions_from_csv(target, csv_path)


def test_import_csv_is_all_or_nothing(workdir: Path) -> None:
    target = workdir / "adjudication"
    target.mkdir()
    shutil.copy2(ADJ_ROOT / "UI-GAME-007.yaml", target / "UI-GAME-007.yaml")
    csv_path = target / "adjudication.csv"
    export_csv(target, csv_path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0].update({"final_validity": "invalid", "adjudicator": "reviewer-1"})
    rows[1].update({"final_validity": "invalid", "final_severity": "blocker", "adjudicator": "reviewer-1"})
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(AdjudicationError):
        import_decisions_from_csv(target, csv_path)
    data = load_case(target / "UI-GAME-007.yaml")
    assert all(item["final"]["validity"] == "pending" for item in data["candidates"])
    assert not (target / "history.jsonl").exists()


def test_import_csv_is_idempotent(workdir: Path) -> None:
    target = workdir / "adjudication"
    target.mkdir()
    shutil.copy2(ADJ_ROOT / "UI-GAME-007.yaml", target / "UI-GAME-007.yaml")
    csv_path = target / "adjudication.csv"
    export_csv(target, csv_path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row.update({"final_validity": "invalid", "adjudicator": "reviewer-1"})
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    first = import_decisions_from_csv(target, csv_path)
    assert first["decisions"] == 6
    history_lines = len((target / "history.jsonl").read_text(encoding="utf-8").splitlines())
    second = import_decisions_from_csv(target, csv_path)
    assert second["decisions"] == 0
    assert second["already_applied"] == 6
    assert len((target / "history.jsonl").read_text(encoding="utf-8").splitlines()) == history_lines


def test_case_verdict_consistency_rules(workdir: Path) -> None:
    target = workdir / "UI-GAME-007.yaml"
    shutil.copy2(ADJ_ROOT / "UI-GAME-007.yaml", target)
    data = load_case(target)
    record_decision(
        data,
        "CAND-UI-GAME-007-01",
        validity="valid",
        severity="major",
        category="状态不自洽",
        adjudicator="reviewer-1",
    )
    for candidate in data["candidates"][1:]:
        record_decision(
            data,
            candidate["candidate_id"],
            validity="invalid",
            adjudicator="reviewer-1",
        )
    with pytest.raises(AdjudicationError, match="pass"):
        set_case_verdict(data, verdict="pass", adjudicator="reviewer-1")
    with pytest.raises(AdjudicationError, match="blocked"):
        set_case_verdict(data, verdict="blocked", adjudicator="reviewer-1")
    with pytest.raises(AdjudicationError, match="defect_count"):
        set_case_verdict(data, verdict="needs_fix", defect_count=3, adjudicator="reviewer-1")
    set_case_verdict(data, verdict="needs_fix", defect_count=1, adjudicator="reviewer-1")
    assert data["case_level"]["verdict"] == "needs_fix"
