"""模型注册表（docs/06 §3.6）：只读配置，不读取供应商密钥值。

校验重点：
- provider 必须已在 `providers` 中声明；
- 真实 Model ID、超时、输出上限、并发必须为正；
- `verification_status` / `data_admission_status` 必须来自 docs/17；
- `api_key_env` 只能是环境变量名，不允许在 YAML 中直接写密钥。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.core.enums import VerificationStatus


class ModelRegistryError(Exception):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: str


@dataclass(frozen=True)
class RoleConfig:
    role: str
    provider: str
    model_id: str
    timeout: float
    max_output_tokens: int
    concurrency: int
    verification_status: str
    data_admission_status: str = "pending"


@dataclass
class ModelRegistry:
    version: str
    providers: dict[str, ProviderConfig]
    roles: dict[str, RoleConfig]
    pricing: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> ModelRegistry:
        try:
            payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ModelRegistryError(f"模型注册表不存在: {path}") from exc
        except yaml.YAMLError as exc:
            raise ModelRegistryError(f"模型注册表不是合法 YAML: {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ModelRegistryError("模型注册表顶层必须是对象")
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ModelRegistry:
        version = str(payload.get("version") or "").strip()
        if not version:
            raise ModelRegistryError("缺少 version")

        raw_providers = payload.get("providers")
        if not isinstance(raw_providers, dict) or not raw_providers:
            raise ModelRegistryError("providers 必须是非空对象")
        providers: dict[str, ProviderConfig] = {}
        for name, spec in raw_providers.items():
            if not isinstance(spec, dict):
                raise ModelRegistryError(f"provider {name} 必须是对象")
            base_url = str(spec.get("base_url") or "").strip()
            api_key_env = str(spec.get("api_key_env") or "").strip()
            if not base_url:
                raise ModelRegistryError(f"provider {name} 缺少 base_url")
            if not api_key_env:
                raise ModelRegistryError(f"provider {name} 缺少 api_key_env")
            if api_key_env.startswith(("sk-", "Bearer ")) or len(api_key_env) > 64:
                raise ModelRegistryError(
                    f"provider {name}.api_key_env 必须是环境变量名，不能写密钥"
                )
            providers[name] = ProviderConfig(
                name=name, base_url=base_url, api_key_env=api_key_env
            )

        raw_roles = payload.get("roles")
        if not isinstance(raw_roles, dict) or not raw_roles:
            raise ModelRegistryError("roles 必须是非空对象")
        roles: dict[str, RoleConfig] = {}
        valid_verification = {item.value for item in VerificationStatus}
        for role, spec in raw_roles.items():
            if not isinstance(spec, dict):
                raise ModelRegistryError(f"role {role} 必须是对象")
            provider = str(spec.get("provider") or "").strip()
            if provider not in providers:
                raise ModelRegistryError(f"role {role} 引用了未声明的 provider {provider!r}")
            model_id = str(spec.get("model_id") or "").strip()
            if not model_id:
                raise ModelRegistryError(f"role {role} 缺少 model_id")
            try:
                timeout = float(spec.get("timeout"))
                max_output = int(spec.get("max_output_tokens"))
                concurrency = int(spec.get("concurrency"))
            except (TypeError, ValueError) as exc:
                raise ModelRegistryError(
                    f"role {role} 的 timeout/max_output_tokens/concurrency 必须是数值"
                ) from exc
            if timeout <= 0 or max_output <= 0 or concurrency <= 0:
                raise ModelRegistryError(
                    f"role {role} 的 timeout/max_output_tokens/concurrency 必须为正"
                )
            status = str(spec.get("verification_status") or "unverified")
            if status not in valid_verification:
                raise ModelRegistryError(
                    f"role {role} 的 verification_status 非法: {status!r}"
                )
            roles[role] = RoleConfig(
                role=role,
                provider=provider,
                model_id=model_id,
                timeout=timeout,
                max_output_tokens=max_output,
                concurrency=concurrency,
                verification_status=status,
                data_admission_status=str(spec.get("data_admission_status") or "pending"),
            )

        pricing = payload.get("pricing") if isinstance(payload.get("pricing"), dict) else {}
        return cls(
            version=version,
            providers=providers,
            roles=roles,
            pricing=pricing,
            raw=payload,
        )

    def role(self, name: str) -> RoleConfig:
        if name not in self.roles:
            raise ModelRegistryError(f"未注册的模型角色: {name!r}")
        return self.roles[name]

    def provider_for(self, role: str) -> ProviderConfig:
        config = self.role(role)
        return self.providers[config.provider]

    def model_ids(self) -> dict[str, str]:
        return {name: config.model_id for name, config in self.roles.items()}

    def missing_api_key_envs(self, environ: dict[str, str]) -> list[str]:
        missing = []
        for provider in self.providers.values():
            if not environ.get(provider.api_key_env):
                missing.append(provider.api_key_env)
        return sorted(set(missing))
