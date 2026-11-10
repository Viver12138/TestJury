"""身份与授权（docs/09 §6、docs/10 §2、docs/17 §5）。

- 角色只来自服务端 API Key 授权表；客户端 `X-Role` 不参与授权，只记日志。
- `actor_type=service` 的系统身份不得审批；`admin` 不自动拥有 `approver`。
- 审批人与提交人分离由服务端按真实身份校验（可配置）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

import structlog
from fastapi import Request

from app.config import Settings
from app.core.enums import ActorType, DecisionValue, Role
from app.core.errors import ApiError, ErrorCode

logger = structlog.get_logger("testjury.auth")

_HASH_PREFIX = b"testjury-api-key:"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(_HASH_PREFIX + raw_key.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApiKeyRecord:
    key_hash: str
    actor_id: str
    actor_type: str
    roles: frozenset[str]
    caller_id: str | None = None
    revoked_at: datetime | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class Principal:
    actor_id: str
    actor_type: ActorType
    roles: frozenset[str]
    caller_id: str | None
    auth_source: str = "api_key"

    def has_role(self, role: Role | str) -> bool:
        return str(role) in self.roles

    def has_any_role(self, *roles: Role | str) -> bool:
        return any(self.has_role(role) for role in roles)


class AuthRepository(Protocol):
    async def find_by_hash(self, key_hash: str) -> ApiKeyRecord | None: ...


@dataclass
class MemoryAuthRepository:
    """单测/本地 Mock 用授权表；生产使用 PostgreSQL `api_keys`。"""

    _records: dict[str, ApiKeyRecord] = field(default_factory=dict)

    def add_key(
        self,
        raw_key: str,
        *,
        actor_id: str,
        actor_type: ActorType | str = ActorType.HUMAN,
        roles: list[Role | str] | None = None,
        caller_id: str | None = None,
        revoked_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> ApiKeyRecord:
        record = ApiKeyRecord(
            key_hash=hash_api_key(raw_key),
            actor_id=actor_id,
            actor_type=str(actor_type),
            roles=frozenset(str(role) for role in (roles or [Role.REVIEWER])),
            caller_id=caller_id,
            revoked_at=revoked_at,
            expires_at=expires_at,
        )
        self._records[record.key_hash] = record
        return record

    async def find_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        return self._records.get(key_hash)


def _now() -> datetime:
    return datetime.now(UTC)


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("authorization")
    if not header:
        raise ApiError(ErrorCode.UNAUTHORIZED, "缺少 Authorization: Bearer <api-key>")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(ErrorCode.UNAUTHORIZED, "Authorization 必须使用 Bearer 方案")
    return token.strip()


async def authenticate_request(request: Request) -> Principal:
    raw_key = _extract_bearer(request)
    repository: AuthRepository | None = getattr(request.app.state, "auth_repository", None)
    if repository is None:  # pragma: no cover - 装配错误
        raise ApiError(ErrorCode.INTERNAL, "授权表未初始化")

    record = await repository.find_by_hash(hash_api_key(raw_key))
    if record is None:
        raise ApiError(ErrorCode.UNAUTHORIZED, "API Key 无效")
    if record.revoked_at is not None:
        raise ApiError(ErrorCode.UNAUTHORIZED, "API Key 已撤销")
    if record.expires_at is not None and record.expires_at <= _now():
        raise ApiError(ErrorCode.UNAUTHORIZED, "API Key 已过期")

    declared_role = request.headers.get("x-role")
    if declared_role and declared_role not in record.roles:
        # 只记日志，不提升权限（ACC-M0-014）
        logger.info(
            "x_role_ignored",
            declared_role=declared_role,
            granted_roles=sorted(record.roles),
            actor_id=record.actor_id,
        )

    try:
        actor_type = ActorType(record.actor_type)
    except ValueError as exc:  # pragma: no cover - 数据错误
        raise ApiError(ErrorCode.INTERNAL, "授权记录 actor_type 非法") from exc

    return Principal(
        actor_id=record.actor_id,
        actor_type=actor_type,
        roles=record.roles,
        caller_id=record.caller_id,
    )


async def get_principal(request: Request) -> Principal:
    """FastAPI 依赖：解析并校验当前调用者身份。"""

    return await authenticate_request(request)


def ensure_roles(principal: Principal, *roles: Role | str) -> None:
    if not principal.has_any_role(*roles):
        raise ApiError(
            ErrorCode.FORBIDDEN,
            f"角色不足：需要 {'/'.join(str(role) for role in roles)}",
        )


def ensure_approval_allowed(principal: Principal, decision: str) -> None:
    """审批接口只接受个人身份；approve/reject 需要 approver 角色。"""

    if principal.actor_type is not ActorType.HUMAN:
        raise ApiError(ErrorCode.FORBIDDEN, "系统身份不得执行人工审批（actor_type=service）")

    if decision == DecisionValue.REQUEST_CHANGES.value:
        ensure_roles(principal, Role.REVIEWER, Role.APPROVER)
    else:
        ensure_roles(principal, Role.APPROVER)


def ensure_approval_separation(
    principal: Principal,
    submitter_id: str | None,
    settings: Settings,
) -> None:
    if not settings.decision_require_separation:
        return
    if submitter_id is None:
        return
    if principal.actor_id == submitter_id:
        logger.info(
            "self_approval_rejected",
            actor_id=principal.actor_id,
            submitter_id=submitter_id,
        )
        raise ApiError(ErrorCode.FORBIDDEN, "审批人不得为用例提交人")
