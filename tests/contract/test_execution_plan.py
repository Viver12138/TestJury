"""执行台账检查的变异测试（补充 16 / docs/30）。

证明台账不是"永远通过"：
1. 实验协议未填阈值却标记 signed → 必须失败；
2. 验证项标记 accepted 但没有验收证据 → 必须失败。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_execution_plan.py"


def _copy_repo(destination: Path) -> Path:
    shutil.copytree(
        REPO_ROOT,
        destination,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc"),
    )
    return destination


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


def test_execution_plan_clean(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path / "clean")
    result = _run_checker(root)
    assert result.returncode == 0, result.stdout + result.stderr


def test_signed_protocol_without_thresholds_fails(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path / "protocol")
    path = root / "design" / "experiment_protocol.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["status"] = "signed"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = _run_checker(root)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "thresholds" in output or "dataset_version" in output, output


def test_accepted_without_evidence_fails(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path / "accepted")
    path = root / "design" / "execution_plan.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    target = next(item for item in data["verification_items"] if item["id"] == "V-01")
    target["status"] = "accepted"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = _run_checker(root)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "acceptance_evidence" in output, output
