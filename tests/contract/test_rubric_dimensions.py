"""业务维度与 Rubric 映射检查的变异测试（BIZ-1 / ACC-BIZ-005）。

验证 docs/00 §5.2 的 11 个业务维度、docs/04 §2.1 映射表与 rubric.yaml 三者一致；
删除任一维度映射必须导致检查失败。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_rubric.py"
STANDARD_DOC = Path("docs") / "04-评审标准.md"



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


def test_dimension_mapping_complete(workdir: Path, repo_copy) -> None:
    root = repo_copy(workdir / "clean")
    result = _run_checker(root)
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_dimension_is_detected(workdir: Path, repo_copy) -> None:
    root = repo_copy(workdir / "mutated")
    path = root / STANDARD_DOC
    text = path.read_text(encoding="utf-8")
    target = "| 10 | 重复与冗余 | T8 | `重复冗余` | 无意义的重复用例或重复步骤 |\n"
    assert target in text, "测试变异点未命中，请检查 docs/04 §2.1 的重复冗余行格式"
    path.write_text(text.replace(target, "", 1), encoding="utf-8")

    result = _run_checker(root)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "业务维度" in output or "§2.1" in output, output
    assert "重复与冗余" in output or "缺少" in output, output



