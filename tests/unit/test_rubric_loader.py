"""ACC-M0-009：Rubric 加载、Schema 与业务校验（docs/04 §9、rubric/README）。"""

from __future__ import annotations

import copy
import shutil
from pathlib import Path

import pytest
import yaml

from app.rubric.loader import RubricError, RubricRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
RUBRIC_DIR = REPO_ROOT / "rubric"


def _copy_rubric(workdir: Path) -> Path:
    target = workdir / "rubric"
    target.mkdir()
    shutil.copy(RUBRIC_DIR / "rubric.yaml", target / "rubric.yaml")
    shutil.copy(RUBRIC_DIR / "schema.json", target / "schema.json")
    shutil.copytree(RUBRIC_DIR / "versions", target / "versions")
    return target


def _write_rubric(target: Path, data: dict) -> None:
    (target / "rubric.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    # 修改主配置后必须同步（或故意不同步）冻结副本，由用例决定
    version = data["version"]
    (target / "versions" / f"v{version}.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def test_active_rubric_loads_with_schema_and_business_rules() -> None:
    repo = RubricRepository(RUBRIC_DIR / "rubric.yaml", RUBRIC_DIR / "schema.json")
    rubric = repo.load_active()
    assert rubric.version == "0.2.0"
    assert rubric.status in {"draft", "reviewed", "published", "deprecated"}
    assert {"B1", "T8", "A6"} <= rubric.checkpoint_ids


def test_production_mode_rejects_draft() -> None:
    repo = RubricRepository(RUBRIC_DIR / "rubric.yaml", RUBRIC_DIR / "schema.json")
    with pytest.raises(RubricError) as excinfo:
        repo.load_active(require_published=True)
    assert "published" in str(excinfo.value)
    assert "draft" in str(excinfo.value)


def test_duplicate_checkpoint_id_is_rejected(workdir: Path) -> None:
    target = _copy_rubric(workdir)
    data = yaml.safe_load((target / "rubric.yaml").read_text(encoding="utf-8"))
    duplicated = copy.deepcopy(data)
    checkpoints = duplicated["dimensions"]["business"]["checkpoints"]
    checkpoints.append({"id": checkpoints[0]["id"], "name": "重复检查点"})
    _write_rubric(target, duplicated)

    repo = RubricRepository(target / "rubric.yaml", target / "schema.json")
    with pytest.raises(RubricError) as excinfo:
        repo.load_active()
    assert "ID 重复" in str(excinfo.value)


def test_unknown_category_dimension_is_rejected(workdir: Path) -> None:
    target = _copy_rubric(workdir)
    data = yaml.safe_load((target / "rubric.yaml").read_text(encoding="utf-8"))
    data["categories"]["覆盖缺失"]["dimensions"].append("unknown_dimension")
    _write_rubric(target, data)

    repo = RubricRepository(target / "rubric.yaml", target / "schema.json")
    with pytest.raises(RubricError) as excinfo:
        repo.load_active()
    assert "unknown_dimension" in str(excinfo.value)


def test_missing_frozen_copy_is_rejected(workdir: Path) -> None:
    target = _copy_rubric(workdir)
    data = yaml.safe_load((target / "rubric.yaml").read_text(encoding="utf-8"))
    (target / "versions" / f"v{data['version']}.yaml").unlink()

    repo = RubricRepository(target / "rubric.yaml", target / "schema.json")
    with pytest.raises(RubricError) as excinfo:
        repo.load_active()
    assert "冻结副本" in str(excinfo.value)


def test_frozen_copy_drift_is_rejected(workdir: Path) -> None:
    target = _copy_rubric(workdir)
    data = yaml.safe_load((target / "rubric.yaml").read_text(encoding="utf-8"))
    data["severity"]["suggestion"] = "被改动的描述"
    (target / "rubric.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    repo = RubricRepository(target / "rubric.yaml", target / "schema.json")
    with pytest.raises(RubricError) as excinfo:
        repo.load_active()
    assert "冻结副本与 rubric.yaml 内容不一致" in str(excinfo.value)


def test_historical_version_can_be_loaded_independently() -> None:
    repo = RubricRepository(RUBRIC_DIR / "rubric.yaml", RUBRIC_DIR / "schema.json")
    historical = repo.load_version("0.1.0")
    assert historical.version == "0.1.0"
    assert "T8" not in historical.checkpoint_ids  # T8 是 0.2.0 新增

    active = repo.load_active()
    assert "T8" in active.checkpoint_ids

