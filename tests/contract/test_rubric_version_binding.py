"""Rubric 版本绑定检查的变异测试（P0-1 / ACC-M0-010）。

验证验收/设计文件不得硬编码历史 Rubric 版本；改回 v0.1.0 必须失败。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_rubric.py"
ACCEPTANCE = Path("design") / "m0_acceptance.yaml"


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


def test_version_binding_clean(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path / "clean")
    result = _run_checker(root)
    assert result.returncode == 0, result.stdout + result.stderr


def test_hardcoded_old_version_is_detected(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path / "mutated")
    path = root / ACCEPTANCE
    text = path.read_text(encoding="utf-8")
    assert "versions/v0.1.0.yaml" not in text
    mutated = text.replace(
        "preconditions: [rubric/rubric.yaml 可加载, rubric/versions/ 目录存在]",
        "preconditions: [rubric/versions/v0.1.0.yaml 存在]",
        1,
    )
    assert mutated != text
    path.write_text(mutated, encoding="utf-8")

    result = _run_checker(root)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "Rubric 版本绑定" in output, output
    assert "v0.1.0" in output, output
