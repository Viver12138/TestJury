"""阶段执行门禁测试（补充 17 P0-03）。

S2 在 owner 未指定时必须失败；且不得因 Rubric 生产发布（V-03）而阻塞 S2。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "check_execution_gate.py"


def test_s2_blocked_by_missing_owner_but_not_v03(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(REPO_ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    env = dict(os.environ)
    env["TJ_REPO_ROOT"] = str(root)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, str(GATE), "--stage", "S2"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(root),
        timeout=120,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "owner" in output, output
    assert "V-03" not in output, output
