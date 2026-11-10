"""契约检查的变异测试（M0-08 / P0-2 ACC-CON-007）。

验证"检查脚本能通过"不等于"检查脚本有效"：
1. 在仓库副本上跑聚合检查，必须通过；
2. 在副本中删除 docs/17 的一个枚举值，检查必须失败，并指出文件与字段。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_contracts.py"
DICT_DOC = Path("docs") / "17-全局数据字典.md"



def _run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["TJ_REPO_ROOT"] = str(root)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(CHECKER), "--only", "docs"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(root),
        timeout=120,
    )


def test_clean_copy_passes(workdir: Path, repo_copy) -> None:
    root = repo_copy(workdir / "clean")
    result = _run_checker(root)
    assert result.returncode == 0, result.stdout + result.stderr


def test_full_contract_check_passes(workdir: Path, repo_copy) -> None:
    root = repo_copy(workdir / "full")
    result = _run_full_checker(root)
    assert result.returncode == 0, result.stdout + result.stderr


def _run_full_checker(root: Path) -> subprocess.CompletedProcess[str]:
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
        timeout=180,
    )


def test_enum_drift_is_detected(workdir: Path, repo_copy) -> None:
    root = repo_copy(workdir / "drifted")
    dictionary = root / DICT_DOC
    original = dictionary.read_text(encoding="utf-8")
    mutated = original.replace("`blocked` / `conditional` / `need_human` / `null`", "`blocked` / `conditional` / `null`", 1)
    assert mutated != original, "测试变异点未命中，请检查 docs/17 的 ai_verdict 行格式"
    dictionary.write_text(mutated, encoding="utf-8")

    result = _run_checker(root)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "ai_verdict" in output, output
    assert "17-全局数据字典.md" in output, output



