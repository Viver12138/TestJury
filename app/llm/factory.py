"""按模型注册表构造适配器（不读取/不打印密钥值）。"""

from __future__ import annotations

import os
from collections.abc import Mapping

from app.llm.adapters.chat import OpenAICompatibleChatAdapter
from app.llm.adapters.embedding import OpenAICompatibleEmbeddingAdapter
from app.llm.adapters.rerank import HttpRerankAdapter
from app.llm.registry import ModelRegistry, ModelRegistryError


class ModelAdapterConfigError(Exception):
    pass


def _api_key(api_key_env: str, environ: Mapping[str, str]) -> str:
    value = environ.get(api_key_env, "")
    return value.strip()


def build_chat_adapter(
    registry: ModelRegistry,
    role: str,
    *,
    environ: Mapping[str, str] | None = None,
    client=None,
) -> OpenAICompatibleChatAdapter:
    environ = environ if environ is not None else os.environ
    config = registry.role(role)
    provider = registry.providers[config.provider]
    api_key = _api_key(provider.api_key_env, environ)
    if not api_key and not provider.base_url.startswith("mock://"):
        raise ModelAdapterConfigError(
            f"provider {config.provider} 缺少密钥环境变量 {provider.api_key_env}"
        )
    if provider.base_url.startswith("mock://"):
        raise ModelAdapterConfigError(
            f"role {role} 仍指向 mock provider；M1 真实调用前必须替换 models.yaml"
        )
    return OpenAICompatibleChatAdapter(
        provider.base_url,
        api_key,
        model_id=config.model_id,
        timeout=config.timeout,
        client=client,
    )


def build_embedding_adapter(
    registry: ModelRegistry,
    *,
    environ: Mapping[str, str] | None = None,
    client=None,
) -> OpenAICompatibleEmbeddingAdapter:
    environ = environ if environ is not None else os.environ
    spec = registry.raw.get("embedding") if isinstance(registry.raw.get("embedding"), dict) else {}
    provider_name = str(spec.get("provider") or "")
    model_id = str(spec.get("model_id") or "")
    dimension = int(spec.get("dimension") or 0)
    if provider_name not in registry.providers or not model_id or dimension <= 0:
        raise ModelAdapterConfigError("embedding 配置不完整（provider/model_id/dimension）")
    provider = registry.providers[provider_name]
    api_key = _api_key(provider.api_key_env, environ)
    if not api_key and not provider.base_url.startswith("mock://"):
        raise ModelAdapterConfigError(f"provider {provider_name} 缺少密钥环境变量")
    return OpenAICompatibleEmbeddingAdapter(
        provider.base_url,
        api_key,
        model_id=model_id,
        dimension=dimension,
        timeout=float(spec.get("timeout") or 30),
        client=client,
    )


def build_rerank_adapter(
    registry: ModelRegistry,
    *,
    environ: Mapping[str, str] | None = None,
    client=None,
) -> HttpRerankAdapter:
    environ = environ if environ is not None else os.environ
    spec = registry.raw.get("rerank") if isinstance(registry.raw.get("rerank"), dict) else {}
    provider_name = str(spec.get("provider") or "")
    model_id = str(spec.get("model_id") or "")
    if provider_name not in registry.providers or not model_id:
        raise ModelAdapterConfigError("rerank 配置不完整（provider/model_id）")
    provider = registry.providers[provider_name]
    api_key = _api_key(provider.api_key_env, environ)
    if not api_key and not provider.base_url.startswith("mock://"):
        raise ModelAdapterConfigError(f"provider {provider_name} 缺少密钥环境变量")
    return HttpRerankAdapter(
        provider.base_url,
        api_key,
        model_id=model_id,
        timeout=float(spec.get("timeout") or 20),
        client=client,
    )


__all__ = [
    "ModelAdapterConfigError",
    "ModelRegistryError",
    "build_chat_adapter",
    "build_embedding_adapter",
    "build_rerank_adapter",
]
