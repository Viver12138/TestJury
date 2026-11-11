"""生产模型准入门禁。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.llm.admission import ModelAdmissionError, enforce_model_admission, load_admission
from app.llm.registry import ModelRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS = REPO_ROOT / "config" / "models.yaml"


def _admission(registry: ModelRegistry, **overrides: object) -> dict:
    roles = []
    for role in ("chief_blind", "jury_a", "jury_b"):
        entry = {
            "role": role,
            "real_model_id": registry.role(role).model_id,
            "verification_status": "verified",
            "data_admission_status": "approved",
            "evidence": ["evidence/V-01/model-smoke.json"],
        }
        entry.update(overrides.get(role, {}))
        roles.append(entry)
    return {"roles": roles}


def _write(tmp_path: Path, payload: dict) -> Path:
    import yaml

    path = tmp_path / "admission.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


def test_load_admission_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ModelAdmissionError):
        load_admission(tmp_path / "missing.yaml")


def test_all_verified_approved_passes(tmp_path: Path) -> None:
    registry = ModelRegistry.load(MODELS)
    path = _write(tmp_path, _admission(registry))
    enforce_model_admission(registry, path)  # 不抛异常


def test_testing_status_rejected(tmp_path: Path) -> None:
    registry = ModelRegistry.load(MODELS)
    payload = _admission(registry, jury_a={"verification_status": "testing"})
    with pytest.raises(ModelAdmissionError, match="jury_a"):
        enforce_model_admission(registry, _write(tmp_path, payload))


def test_data_admission_pending_rejected(tmp_path: Path) -> None:
    registry = ModelRegistry.load(MODELS)
    payload = _admission(registry, chief_blind={"data_admission_status": "pending"})
    with pytest.raises(ModelAdmissionError, match="data_admission_status"):
        enforce_model_admission(registry, _write(tmp_path, payload))


def test_masking_requires_explicit_policy(tmp_path: Path) -> None:
    registry = ModelRegistry.load(MODELS)
    payload = _admission(registry, jury_b={"data_admission_status": "approved_with_masking"})
    path = _write(tmp_path, payload)
    with pytest.raises(ModelAdmissionError, match="MASKING_POLICY_ENABLED"):
        enforce_model_admission(registry, path, masking_enabled=False)
    enforce_model_admission(registry, path, masking_enabled=True)


def test_model_id_mismatch_rejected(tmp_path: Path) -> None:
    registry = ModelRegistry.load(MODELS)
    payload = _admission(registry, jury_a={"real_model_id": "wrong-model"})
    with pytest.raises(ModelAdmissionError, match="注册表"):
        enforce_model_admission(registry, _write(tmp_path, payload))


def test_production_app_refuses_unverified_models(tmp_path: Path) -> None:
    from app.main import create_app
    from tests.helpers import make_settings

    settings = make_settings(
        app_env="prod",
        storage_backend="postgres",
        review_model_mode="live",
        bootstrap_api_keys="",
        model_admission_path=str(REPO_ROOT / "design" / "model_admission.yaml"),
        enforce_model_admission=True,
    )
    with pytest.raises(ModelAdmissionError):
        create_app(settings, run_worker=False)
