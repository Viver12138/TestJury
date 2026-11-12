"""版本号计算（docs/06 §3.5）：启动时缓存，创建任务时冻结写入 `review_jobs`。

M0 尚未接入知识库与真实 Prompt 模板：
- `kb_*` 固定为 `kb-none`，接入 KB 后改为内容哈希 + active build 版本；
- `prompts` 取注册表版本值，`prompt_version_hash` 为注册表内容哈希；
- `embedding_profile` 由 provider/model/version/维度唯一确定。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.config import Settings
from app.rubric.loader import RubricRepository


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path, *, length: int = 12) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:length]


@dataclass(frozen=True)
class Versions:
    kb_content_version: str
    kb_build_version: str
    rubric: str
    prompts: dict[str, str]
    prompt_version_hash: str
    retrieval_config: str
    embedding_profile: str
    model_config: str
    models: dict[str, str] = field(default_factory=dict)
    price_config: str = "price-unverified"

    def report_versions(self) -> dict[str, Any]:
        return {
            "kb": self.kb_build_version,
            "kb_content_version": self.kb_content_version,
            "kb_build_version": self.kb_build_version,
            "rubric": self.rubric,
            "prompts": dict(self.prompts),
            "retrieval_config": self.retrieval_config,
            "embedding_profile": self.embedding_profile,
            "model_config": self.model_config,
            "models": dict(self.models),
            "price_config": self.price_config,
        }

    def idempotency_components(self) -> dict[str, str]:
        return {
            "kb_build_version": self.kb_build_version,
            "rubric_version": self.rubric,
            "prompt_version_hash": self.prompt_version_hash,
            "embedding_profile_id": self.embedding_profile,
            "retrieval_config_version": self.retrieval_config,
            "model_config_version": self.model_config,
        }


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def compute_versions(settings: Settings) -> Versions:
    rubric_repo = RubricRepository(settings.rubric_path, settings.rubric_path.parent / "schema.json")
    rubric = rubric_repo.load_active()

    prompt_registry = _load_yaml(settings.prompt_registry_path)
    prompts = {
        str(name): str(spec.get("version"))
        for name, spec in (prompt_registry.get("prompts") or {}).items()
        if isinstance(spec, dict) and spec.get("version")
    }
    prompt_version_hash = (
        file_sha256(settings.prompt_registry_path, length=12)
        if settings.prompt_registry_path.exists()
        else sha256_text(json.dumps(prompts, sort_keys=True))[:12]
    )
    # Prompt templates currently live in Python; registry labels alone cannot freeze their content.
    prompt_version_hash = sha256_text(prompt_version_hash + file_sha256(
        Path(__file__).resolve().parents[1] / "llm/review.py", length=64))

    model_registry = _load_yaml(settings.model_registry_path)
    model_config = (
        file_sha256(settings.model_registry_path, length=8)
        if settings.model_registry_path.exists()
        else sha256_text(json.dumps(model_registry, sort_keys=True))[:8]
    )
    models = {
        str(role): str(spec.get("model_id"))
        for role, spec in (model_registry.get("roles") or {}).items()
        if isinstance(spec, dict) and spec.get("model_id")
    }
    price_config = str(
        (model_registry.get("pricing") or {}).get("version") or "price-unverified"
    )

    retrieval_params = {
        "implementation": file_sha256(Path(__file__).resolve().parents[1] / "knowledge/runtime.py", length=64),
        "query_max": settings.retrieval_query_max,
        "top_k_keyword": settings.retrieval_top_k_keyword,
        "top_k_vector": settings.retrieval_top_k_vector,
        "top_n_rerank": settings.retrieval_top_n_rerank,
        "rrf_k": settings.rrf_k,
        "context_top_k": settings.kb_context_top_k,
        "context_token_cap": settings.kb_context_token_cap,
        "fusion_sim": settings.fusion_sim_threshold,
        "fusion_suspect": settings.fusion_suspect_threshold,
        "step_tolerance": settings.step_tolerance,
    }
    retrieval_config = settings.retrieval_config_version or sha256_text(
        json.dumps(retrieval_params, sort_keys=True)
    )[:8]

    embedding_profile = (
        f"{settings.embedding_provider}:{settings.embedding_model}"
        f"@{settings.embedding_model_version}/{settings.embedding_dimension}/cosine"
    )
    if settings.knowledge_vector_enabled:
        actual = model_registry.get("embedding") or {}
        configured = (settings.embedding_provider, settings.embedding_model, settings.embedding_dimension)
        if configured != (actual.get("provider"), actual.get("model_id"), actual.get("dimension")):
            raise ValueError("Embedding profile differs from the model registry; align configuration before starting")

    return Versions(
        kb_content_version="kb-none",
        kb_build_version="kb-none",
        rubric=rubric.version,
        prompts=prompts,
        prompt_version_hash=prompt_version_hash,
        retrieval_config=retrieval_config,
        embedding_profile=embedding_profile,
        model_config=model_config,
        models=models,
        price_config=price_config,
    )
