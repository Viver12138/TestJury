"""模型注册表与适配器工厂契约（不访问网络、不读取真实密钥）。"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from app.llm.factory import (
    ModelAdapterConfigError,
    build_chat_adapter,
    build_embedding_adapter,
    build_rerank_adapter,
)
from app.llm.registry import ModelRegistry, ModelRegistryError

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_PATH = REPO_ROOT / "config" / "models.yaml"


def _config() -> dict:
    return {
        "version": "models-test",
        "providers": {
            "vendor": {"base_url": "https://vendor.example/v1", "api_key_env": "VENDOR_API_KEY"}
        },
        "roles": {
            "chief_blind": {
                "provider": "vendor",
                "model_id": "vendor-chief-2026-10",
                "timeout": 120,
                "max_output_tokens": 4096,
                "concurrency": 4,
                "verification_status": "verified",
                "data_admission_status": "approved",
            }
        },
        "embedding": {
            "provider": "vendor",
            "model_id": "vendor-embedding",
            "dimension": 1024,
            "timeout": 30,
        },
        "rerank": {"provider": "vendor", "model_id": "vendor-rerank", "timeout": 20},
    }


def test_repository_config_loads() -> None:
    registry = ModelRegistry.load(MODELS_PATH)
    assert registry.version
    assert "chief_blind" in registry.roles
    assert registry.provider_for("chief_blind").name == "mock"
    assert set(registry.model_ids()) >= {"chief_blind", "jury_a", "jury_b"}


def test_unknown_role_is_rejected() -> None:
    registry = ModelRegistry.from_dict(_config())
    with pytest.raises(ModelRegistryError):
        registry.role("ghost")


def test_undeclared_provider_is_rejected() -> None:
    payload = _config()
    payload["roles"]["chief_blind"]["provider"] = "ghost"
    with pytest.raises(ModelRegistryError):
        ModelRegistry.from_dict(payload)


def test_invalid_verification_status_is_rejected() -> None:
    payload = _config()
    payload["roles"]["chief_blind"]["verification_status"] = "maybe"
    with pytest.raises(ModelRegistryError):
        ModelRegistry.from_dict(payload)


def test_secret_in_config_is_rejected() -> None:
    payload = _config()
    payload["providers"]["vendor"]["api_key_env"] = "sk-live-abcdef123456"
    with pytest.raises(ModelRegistryError):
        ModelRegistry.from_dict(payload)


def test_missing_api_key_env_is_reported_without_reading_values() -> None:
    registry = ModelRegistry.from_dict(_config())
    assert registry.missing_api_key_envs({}) == ["VENDOR_API_KEY"]
    assert registry.missing_api_key_envs({"VENDOR_API_KEY": "x"}) == []


def test_factory_requires_key_and_builds_adapters() -> None:
    registry = ModelRegistry.from_dict(_config())
    with pytest.raises(ModelAdapterConfigError):
        build_chat_adapter(registry, "chief_blind", environ={})

    adapter = build_chat_adapter(
        registry, "chief_blind", environ={"VENDOR_API_KEY": "test-key"}
    )
    assert adapter.model_id == "vendor-chief-2026-10"
    assert adapter.api_key == "test-key"

    embedding = build_embedding_adapter(
        registry, environ={"VENDOR_API_KEY": "test-key"}
    )
    assert embedding.dimension == 1024
    rerank = build_rerank_adapter(registry, environ={"VENDOR_API_KEY": "test-key"})
    assert rerank.model_id == "vendor-rerank"


def test_factory_rejects_mock_provider_for_real_calls() -> None:
    registry = ModelRegistry.load(MODELS_PATH)
    with pytest.raises(ModelAdapterConfigError):
        build_chat_adapter(registry, "chief_blind", environ={})


def test_negative_or_zero_limits_are_rejected() -> None:
    payload = copy.deepcopy(_config())
    payload["roles"]["chief_blind"]["max_output_tokens"] = 0
    with pytest.raises(ModelRegistryError):
        ModelRegistry.from_dict(payload)
