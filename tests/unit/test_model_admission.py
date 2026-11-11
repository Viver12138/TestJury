"""生产模型准入门禁。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from app.llm.admission import ModelAdmissionError, enforce_model_admission, load_admission
from app.llm.registry import ModelRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS = REPO_ROOT / "config" / "models.yaml"


def _admission(registry: ModelRegistry, tmp_path: Path, **overrides: object) -> dict:
    evidence = tmp_path / "model-evidence.json"
    evidence.write_text('{"ok": true}', encoding="utf-8")
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    dpa = tmp_path / "dpa.txt"
    dpa.write_text("signed dpa", encoding="utf-8")
    dpa_digest = hashlib.sha256(dpa.read_bytes()).hexdigest()
    roles = []
    for role in ("chief_blind", "jury_a", "jury_b"):
        entry = {
            "role": role,
            "real_model_id": registry.role(role).model_id,
            "verification_status": "verified",
            "data_admission_status": "approved",
            "reviewer": "reviewer-1",
            "dpa_signed": True,
            "dpa": {
                "document": str(dpa),
                "sha256": dpa_digest,
                "supplier": registry.role(role).provider,
                "models": [registry.role(role).model_id],
                "data_levels": ["public", "internal"],
                "signed_at": "2026-01-01",
                "expires_at": "2030-01-01",
            },
            "allowed_data_level": ["public", "internal"],
            "allow_raw_case": True,
            "requires_masking": False,
            "evidence": [str(evidence)],
            "evidence_hashes": {str(evidence): digest},
        }
        entry.update(overrides.get(role, {}))
        roles.append(entry)
    return {"roles": roles}


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "admission.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


def test_load_admission_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ModelAdmissionError):
        load_admission(tmp_path / "missing.yaml")


def test_all_verified_approved_passes(tmp_path: Path) -> None:
    registry = ModelRegistry.load(MODELS)
    path = _write(tmp_path, _admission(registry, tmp_path))
    enforce_model_admission(registry, path)


def test_testing_status_rejected(tmp_path: Path) -> None:
    registry = ModelRegistry.load(MODELS)
    payload = _admission(registry, tmp_path, jury_a={"verification_status": "testing"})
    with pytest.raises(ModelAdmissionError, match="jury_a"):
        enforce_model_admission(registry, _write(tmp_path, payload))


def test_data_admission_pending_rejected(tmp_path: Path) -> None:
    registry = ModelRegistry.load(MODELS)
    payload = _admission(registry, tmp_path, chief_blind={"data_admission_status": "pending"})
    with pytest.raises(ModelAdmissionError, match="data_admission_status"):
        enforce_model_admission(registry, _write(tmp_path, payload))


def test_masking_requires_real_policy_and_fields(tmp_path: Path) -> None:
    registry = ModelRegistry.load(MODELS)
    payload = _admission(
        registry,
        tmp_path,
        jury_b={
            "data_admission_status": "approved_with_masking",
            "requires_masking": True,
            "allow_raw_case": False,
            "masking_policy_id": "mask-pii-v1",
        },
    )
    path = _write(tmp_path, payload)
    with pytest.raises(ModelAdmissionError, match="MASKING_POLICY_ENABLED"):
        enforce_model_admission(registry, path, masking_enabled=False)
    with pytest.raises(ModelAdmissionError, match="脱敏策略"):
        enforce_model_admission(
            registry, path, masking_enabled=True, masking_policy_id="wrong-policy"
        )
    enforce_model_admission(
        registry, path, masking_enabled=True, masking_policy_id="mask-pii-v1"
    )


def test_model_id_mismatch_rejected(tmp_path: Path) -> None:
    registry = ModelRegistry.load(MODELS)
    payload = _admission(registry, tmp_path, jury_a={"real_model_id": "wrong-model"})
    with pytest.raises(ModelAdmissionError, match="注册表"):
        enforce_model_admission(registry, _write(tmp_path, payload))


def test_expired_dpa_rejected(tmp_path: Path) -> None:
    registry = ModelRegistry.load(MODELS)
    payload = _admission(registry, tmp_path)
    payload["roles"][0]["dpa"]["expires_at"] = "2020-01-01"
    with pytest.raises(ModelAdmissionError, match="过期"):
        enforce_model_admission(registry, _write(tmp_path, payload))


def test_missing_reviewer_and_bad_evidence_rejected(tmp_path: Path) -> None:
    registry = ModelRegistry.load(MODELS)
    payload = _admission(registry, tmp_path, jury_a={"reviewer": ""})
    with pytest.raises(ModelAdmissionError, match="reviewer"):
        enforce_model_admission(registry, _write(tmp_path, payload))

    payload = _admission(registry, tmp_path)
    payload["roles"][0]["evidence_hashes"] = {"x": "bad"}
    with pytest.raises(ModelAdmissionError, match="hash"):
        enforce_model_admission(registry, _write(tmp_path, payload))


def test_data_level_rejected(tmp_path: Path) -> None:
    registry = ModelRegistry.load(MODELS)
    payload = _admission(registry, tmp_path, **{"chief_blind": {"allowed_data_level": ["public"]}})
    with pytest.raises(ModelAdmissionError, match="数据级别"):
        enforce_model_admission(registry, _write(tmp_path, payload), request_data_level="internal")


def test_production_app_refuses_unverified_models() -> None:
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
