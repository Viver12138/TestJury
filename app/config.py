"""集中配置：pydantic-settings 读取环境变量与 .env。

约定（docs/06 §2）：
- `DATABASE_URL` 必填；缺失时服务必须快速失败，不得带默认值带病启动（ACC-M0-002）。
- 生产环境禁止 `STORAGE_BACKEND=memory`，也不接受未验证模型进入正式拓扑。
- 密钥只从环境读取，不写入默认值、日志或错误信息。
"""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class AppEnv(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class BootstrapKey(BaseSettings):
    """首次启动引导用的开发 Key（生产禁用）。

    `key` 为明文，仅用于 dev/test 播种；落库时只保存 sha256 摘要。
    """

    model_config = SettingsConfigDict(extra="forbid")

    key: str = Field(min_length=8)
    actor_id: str = Field(min_length=1)
    actor_type: Literal["service", "human"] = "human"
    roles: list[str] = Field(default_factory=lambda: ["reviewer"])
    caller_id: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 服务 ──
    app_env: AppEnv = AppEnv.DEV
    service_name: str = "testjury"
    worker_concurrency: int = Field(default=4, ge=1, le=64)
    job_timeout_seconds: int = Field(default=1200, ge=1)
    model_timeout_seconds: int = Field(default=120, ge=1)

    # ── 阶段超时（docs/13 §3） ──
    stage_timeout_preprocess: int = 60
    stage_timeout_kb: int = 60
    stage_timeout_blind: int = 240
    stage_timeout_fusion: int = 30
    stage_timeout_vote: int = 180
    stage_timeout_arbitration: int = 180
    stage_timeout_verdict: int = 15
    stage_timeout_render: int = 30
    stage_timeout_db: int = 10

    # ── 队列 ──
    queue_lease_seconds: int = Field(default=300, ge=30)
    queue_max_attempts: int = Field(default=3, ge=1)
    queue_poll_interval_ms: int = Field(default=500, ge=50)
    max_queue_depth: int = Field(default=500, ge=1)

    # ── 数据库 / 存储 ──
    database_url: str
    storage_backend: Literal["postgres", "memory"] = "postgres"
    alembic_database_url: str | None = None
    run_worker: bool = True

    # ── 注册表与输入 ──
    model_registry_path: Path = REPO_ROOT / "config" / "models.yaml"
    prompt_registry_path: Path = REPO_ROOT / "config" / "prompts.yaml"
    input_max_chars: int = Field(default=20000, ge=1)
    attachment_dir: Path = REPO_ROOT / "data" / "attachments"
    attachment_max_mb: int = Field(default=20, ge=1)
    attachment_allowed_mime: str = "image/png,image/jpeg,application/pdf,text/plain"

    # ── 版本与契约 ──
    rubric_path: Path = REPO_ROOT / "rubric" / "rubric.yaml"
    report_schema_path: Path = REPO_ROOT / "schemas" / "report.schema.json"
    report_schema_version: str = "report-1.0"
    kb_content_dir: Path = REPO_ROOT / "kb_content"
    retrieval_config_version: str | None = None

    # ── 检索 / 融合（M0 仅参与版本号计算） ──
    retrieval_query_max: int = 12
    retrieval_top_k_keyword: int = 40
    retrieval_top_k_vector: int = 40
    retrieval_top_n_rerank: int = 40
    rrf_k: int = 60
    kb_context_top_k: int = 10
    kb_context_token_cap: int = 15000
    embedding_provider: str = "qwen"
    embedding_model: str = "qwen3.7-text-embedding-flash"
    embedding_model_version: str = "v1"
    embedding_dimension: int = 1024
    rerank_provider: str = "qwen"
    rerank_model: str = "qwen3.7-text-rerank"
    fusion_sim_threshold: float = 0.86
    fusion_suspect_threshold: float = 0.70
    step_tolerance: int = 1

    # ── 拓扑与降级 ──
    min_participants: int = Field(default=2, ge=0, le=3)
    chief_required: bool = True
    review_topology: Literal["single", "dual", "multi"] = "multi"

    # ── 审批与业务边界 ──
    decision_require_separation: bool = True
    decision_max_history: int = 0
    test_type_default_policy: Literal["strict", "compat"] = "strict"
    test_type_compat_callers: str = ""

    # ── 预算（M0 记录，不在本轮强制） ──
    review_budget_tokens: int = 60000
    review_budget_cost: float = 2.0
    batch_budget_cost: float = 60.0
    daily_budget_cost: float = 500.0

    # ── Webhook ──
    webhook_secret: str = "change-me"
    webhook_max_retries: int = 5
    webhook_timeout_seconds: int = 10

    # ── 开发引导 ──
    bootstrap_api_keys: str = ""

    # ── 校验 ──

    @field_validator("database_url")
    @classmethod
    def _require_database_url(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("DATABASE_URL 不能为空")
        return value.strip()

    @model_validator(mode="after")
    def _guard_production(self) -> Settings:
        if self.app_env is AppEnv.PROD:
            if self.storage_backend == "memory":
                raise ValueError("生产环境禁止 STORAGE_BACKEND=memory")
            if self.bootstrap_api_keys.strip():
                raise ValueError("生产环境禁止 BOOTSTRAP_API_KEYS")
        return self

    # ── 派生属性 ──

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PROD

    @property
    def allowed_mime_types(self) -> list[str]:
        return [item.strip() for item in self.attachment_allowed_mime.split(",") if item.strip()]

    @property
    def compat_callers(self) -> list[str]:
        return [item.strip() for item in self.test_type_compat_callers.split(",") if item.strip()]

    def bootstrap_keys(self) -> list[BootstrapKey]:
        raw = self.bootstrap_api_keys.strip()
        if not raw:
            return []
        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError as exc:  # pragma: no cover - 明确报错而非猜测
            raise ValueError(f"BOOTSTRAP_API_KEYS 不是合法 JSON: {exc.msg}") from exc
        if not isinstance(payload, list):
            raise ValueError("BOOTSTRAP_API_KEYS 必须是 JSON 数组")
        return [BootstrapKey.model_validate(item) for item in payload]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()


def load_settings_or_exit() -> Settings:
    """启动入口使用：缺配置时打印缺失字段并以非 0 退出。

    只输出字段名与原因，不输出配置值（避免泄露密钥，ACC-M0-002）。
    """

    try:
        return get_settings()
    except ValidationError as exc:
        missing = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"])
            missing.append(f"{location.upper()}: {error['msg']}")
        raise SystemExit("缺少或非法配置，服务未启动：\n  " + "\n  ".join(missing)) from None
