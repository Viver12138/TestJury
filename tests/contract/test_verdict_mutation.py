"""Verdict 用例检查的变异测试（P0-4 / ACC-CON-009）。

证明用例检查不是"永远通过"：把一条用例的期望值改错，检查必须失败并指出用例 ID。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_verdict_cases.py"
CASES = Path("design") / "verdict_cases.yaml"


def _run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["TJ_REPO_ROOT"] = str(root)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(CHECKER)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(root),
        timeout=120,
    )


def test_clean_cases_pass(tmp_path: Path) -> None:
    root = tmp_path / "clean"
    shutil.copytree(REPO_ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    result = _run_checker(root)
    assert result.returncode == 0, result.stdout + result.stderr


def test_wrong_expectation_is_detected(tmp_path: Path) -> None:
    root = tmp_path / "mutated"
    shutil.copytree(REPO_ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    path = root / CASES
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    target = next(case for case in data["cases"] if case["id"] == "VC-001")
    assert target["expected"]["ai_verdict"] == "blocked"
    target["expected"]["ai_verdict"] = "conditional"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = _run_checker(root)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "VC-001" in output, output
    assert "ai_verdict" in output, output
