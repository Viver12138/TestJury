"""Rubric 版本绑定检查的变异测试（P0-1 / ACC-M0-010）。

验证验收/设计文件不得硬编码历史 Rubric 版本；改回 v0.1.0 必须失败。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from app.rubric.loader import RubricRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_rubric.py"
ACCEPTANCE = Path("design") / "m0_acceptance.yaml"
RUBRIC_DIR = REPO_ROOT / "rubric"



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


def test_version_binding_clean(workdir: Path, repo_copy) -> None:
    root = repo_copy(workdir / "clean")
    result = _run_checker(root)
    assert result.returncode == 0, result.stdout + result.stderr


def test_hardcoded_old_version_is_detected(workdir: Path, repo_copy) -> None:
    root = repo_copy(workdir / "mutated")
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


def test_version_is_not_hardcoded_and_copy_is_resolvable() -> None:
    data = yaml.safe_load((RUBRIC_DIR / "rubric.yaml").read_text(encoding="utf-8"))
    version = str(data["version"])
    frozen = RUBRIC_DIR / "versions" / f"v{version}.yaml"
    assert frozen.exists(), f"缺少当前版本冻结副本: {frozen}"

    repository = RubricRepository(RUBRIC_DIR / "rubric.yaml", RUBRIC_DIR / "schema.json")
    active = repository.load_active()
    assert active.version == version


def test_historical_report_can_load_its_rubric_version() -> None:
    """历史报告按当时 rubric_version 读取规则，不受新版本影响。"""

    report_fixture = {
        "report_schema_version": "report-1.0",
        "versions": {"rubric": "0.1.0"},
    }
    repository = RubricRepository(RUBRIC_DIR / "rubric.yaml", RUBRIC_DIR / "schema.json")
    historical = repository.load_version(report_fixture["versions"]["rubric"])
    assert historical.version == "0.1.0"
    assert "T8" not in historical.checkpoint_ids
    current = repository.load_active()
    assert current.version != historical.version
    assert "T8" in current.checkpoint_ids


def test_missing_frozen_copy_fails_explicitly(workdir: Path, repo_copy) -> None:
    root = repo_copy(workdir / "missing-copy")
    rubric_path = root / "rubric" / "rubric.yaml"
    data = yaml.safe_load(rubric_path.read_text(encoding="utf-8"))
    (root / "rubric" / "versions" / f"v{data['version']}.yaml").unlink()

    repository = RubricRepository(rubric_path, root / "rubric" / "schema.json")
    try:
        repository.load_active()
    except Exception as exc:
        assert "冻结副本" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("缺少冻结副本时必须失败")



