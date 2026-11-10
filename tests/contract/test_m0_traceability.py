"""ACC-CON-008：M0 十项退出条件全部有可执行用例（追踪字段与测试文件存在）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES = REPO_ROOT / "design" / "m0_acceptance.yaml"


def test_traceability_checker_passes() -> None:
    process = subprocess.run(
        [sys.executable, "scripts/check_m0_acceptance.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert process.returncode == 0, process.stdout + process.stderr


def test_every_case_has_executable_test_file() -> None:
    data = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    missing: list[str] = []
    for case in data["cases"]:
        test_file = case.get("test_file")
        if not test_file:
            missing.append(f"{case['id']}: 缺少 test_file")
            continue
        if not (REPO_ROOT / test_file).exists():
            missing.append(f"{case['id']}: {test_file} 不存在")
        if not case.get("automation"):
            missing.append(f"{case['id']}: 缺少 automation")
        if not case.get("ci_job"):
            missing.append(f"{case['id']}: 缺少 ci_job")
    assert missing == []


def test_exit_conditions_are_all_covered() -> None:
    data = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    covered = {case["maps_to"] for case in data["cases"]}
    for condition in data["exit_conditions"]:
        assert condition["id"] in covered, condition["id"]
