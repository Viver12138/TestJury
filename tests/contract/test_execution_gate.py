"""阶段执行门禁测试（补充 17 P0-03）。

S2 在 owner 未指定时必须失败；且不得因 Rubric 生产发布（V-03）而阻塞 S2。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "check_execution_gate.py"


def _run_gate(root: Path, stage: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["TJ_REPO_ROOT"] = str(root)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(GATE), "--stage", stage],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(root),
        timeout=120,
    )


def test_s2_blocked_by_missing_owner_but_not_v03(workdir: Path, repo_copy) -> None:
    root = repo_copy(workdir / "repo")
    result = _run_gate(root, "S2")
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "owner" in output, output
    assert "V-03" not in output, output


def test_s2_owner_assigned_but_not_verified_fails(workdir: Path, repo_copy) -> None:
    root = repo_copy(workdir / "status")
    path = root / "design" / "execution_plan.yaml"
    plan = yaml.safe_load(path.read_text(encoding="utf-8"))
    for item in plan["verification_items"]:
        if item["id"] in ("V-01", "V-02", "V-04"):
            item["owner"] = "tester"
    path.write_text(yaml.safe_dump(plan, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = _run_gate(root, "S2")
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "至少 verified" in output, output


def test_s1_owner_without_decision_record_fails(workdir: Path, repo_copy) -> None:
    root = repo_copy(workdir / "decision")
    path = root / "design" / "execution_plan.yaml"
    plan = yaml.safe_load(path.read_text(encoding="utf-8"))
    for item in plan["open_items"]:
        if item["id"] in ("Q-07", "Q-08", "Q-09", "Q-12", "Q-13"):
            item["owner"] = "owner"
            if item["id"] == "Q-08":
                item.pop("decision_ref", None)
    path.write_text(yaml.safe_dump(plan, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = _run_gate(root, "S1")
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "decision_ref" in output, output

