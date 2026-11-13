"""FastAPI 应用装配。

设计要点：
- 配置在启动时校验（缺 DATABASE_URL 直接失败，不监听端口）；
- 版本号在启动时计算并缓存（任务创建时冻结，不在恢复时切换）；
- 存储与授权表通过 `app.state` 注入，测试可替换为内存实现；
- Worker 可选启动（`RUN_WORKER`），M0 测试可显式驱动 `worker.run_once()`。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from app import __version__
from app.api import attachments as attachments_api
from app.api import batches as batches_api
from app.api import console as console_api
from app.api import excel_import as excel_import_api
from app.api import health as health_api
from app.api import knowledge as knowledge_api
from app.api import review_tasks as review_tasks_api
from app.api import reviews as reviews_api
from app.config import Settings, get_settings
from app.core.auth import AuthRepository, MemoryAuthRepository
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging
from app.core.observability import RequestContextMiddleware
from app.core.versioning import compute_versions
from app.core.webhooks import WebhookWorker
from app.knowledge.runtime import KnowledgeService, MemoryKnowledgeStore
from app.llm.factory import build_chat_adapter
from app.llm.masking import MaskingPolicy
from app.llm.mock import MockChatClient
from app.llm.registry import ModelRegistry
from app.llm.review import ChatReviewModel
from app.pipeline.orchestrator import ReviewPipeline
from app.rubric.loader import RubricRepository
from app.services.attachments import AttachmentService
from app.services.batches import BatchService
from app.services.decisions import DecisionService
from app.services.reviews import ReviewService
from app.services.tasks import ReviewTaskService
from app.storage.memory import MemoryStorage
from app.storage.port import Storage

# 供应商 Key 通过环境变量传给 Adapter；本地开发从 .env 加载（已存在的环境变量优先）
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger("testjury.app")

_logging_configured = False


def _build_review_model(settings: Settings):
    """mock：离线确定性；live：按 models.yaml 构造真实三模型。"""

    if settings.review_model_mode == "mock":
        return MockChatClient()
    registry = ModelRegistry.load(settings.model_registry_path)
    roles = settings.review_roles
    if settings.is_production and settings.enforce_model_admission:
        from app.llm.admission import enforce_model_admission

        enforce_model_admission(
            registry,
            Path(settings.model_admission_path),
            roles=roles,
            masking_enabled=settings.masking_policy_enabled,
            masking_policy_id=settings.masking_policy_id if settings.masking_policy_enabled else None,
            request_data_level=settings.data_level,
        )
    adapters = {
        role: build_chat_adapter(registry, role)
        for role in roles
    }
    rubric = RubricRepository(
        settings.rubric_path, settings.rubric_path.parent / "schema.json"
    ).load_active()
    masking = (
        MaskingPolicy(
            policy_id=settings.masking_policy_id,
            version=settings.masking_policy_version,
        )
        if settings.masking_policy_enabled
        else None
    )
    return ChatReviewModel(registry, adapters, rubric=rubric, masking_policy=masking)


def _build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "memory":
        return MemoryStorage()
    from app.storage.postgres import PostgresStorage

    return PostgresStorage(settings.database_url)


def _build_auth_repository(settings: Settings) -> AuthRepository:
    if settings.storage_backend == "memory":
        return MemoryAuthRepository()
    from app.storage.postgres import PostgresAuthRepository

    return PostgresAuthRepository(settings.database_url)


def create_app(
    settings: Settings | None = None,
    *,
    storage: Storage | None = None,
    auth_repository: AuthRepository | None = None,
    run_worker: bool | None = None,
) -> FastAPI:
    global _logging_configured
    settings = settings or get_settings()
    if not _logging_configured:
        configure_logging(level="INFO" if settings.is_production else "DEBUG")
        _logging_configured = True

    versions = compute_versions(settings)
    storage = storage or _build_storage(settings)
    auth_repository = auth_repository or _build_auth_repository(settings)

    knowledge = None
    if settings.knowledge_enabled:
        if settings.storage_backend == "memory":
            knowledge_store = MemoryKnowledgeStore()
        else:
            from app.knowledge.postgres import PostgresKnowledgeStore

            knowledge_store = PostgresKnowledgeStore(settings.database_url)
        embedder = None
        profile = "lexical-only"
        if settings.knowledge_vector_enabled:
            from app.llm.factory import build_embedding_adapter

            embedder = build_embedding_adapter(ModelRegistry.load(settings.model_registry_path))
            profile = versions.embedding_profile
        knowledge = KnowledgeService(knowledge_store, embedder=embedder, profile=profile)
    review_service = ReviewService(storage, settings, versions, knowledge)
    decision_service = DecisionService(storage, settings)
    task_service = ReviewTaskService(storage)
    batch_service = BatchService(storage, settings, versions, review_service)
    attachment_service = AttachmentService(storage, settings)
    review_model = _build_review_model(settings)
    pipeline = ReviewPipeline(storage, settings, model=review_model, knowledge=knowledge)

    from app.core.worker import Worker

    worker = Worker(storage, settings, versions, pipeline)
    webhook_worker = WebhookWorker(storage, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await _seed_auth(settings, auth_repository)
        if (settings.run_worker if run_worker is None else run_worker):
            worker.start()
            if settings.webhook_enabled:
                webhook_worker.start()
        try:
            yield
        finally:
            await worker.stop()
            await webhook_worker.stop()
            if knowledge is not None:
                for component in (knowledge.embedder, knowledge.reranker, knowledge.store):
                    close_component = getattr(component, "aclose", None) or getattr(component, "close", None)
                    if close_component is not None:
                        await close_component()
            close_model = getattr(review_model, "aclose", None)
            if close_model is not None:
                await close_model()
            close = getattr(storage, "close", None)
            if close is not None:
                await close()
            close_auth = getattr(auth_repository, "close", None)
            if close_auth is not None:
                await close_auth()

    app = FastAPI(
        title="评审团 Agent",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.webhook_worker = webhook_worker
    app.state.versions = versions
    app.state.storage = storage
    app.state.auth_repository = auth_repository
    app.state.review_service = review_service
    app.state.decision_service = decision_service
    app.state.task_service = task_service
    app.state.batch_service = batch_service
    app.state.attachment_service = attachment_service
    app.state.pipeline = pipeline
    app.state.knowledge = knowledge
    app.state.review_model = review_model
    app.state.worker = worker

    app.add_middleware(RequestContextMiddleware)
    install_exception_handlers(app)

    app.include_router(health_api.router)
    app.include_router(console_api.router)
    app.include_router(excel_import_api.router)
    app.include_router(knowledge_api.router)
    app.include_router(reviews_api.router)
    app.include_router(batches_api.router)
    app.include_router(review_tasks_api.router)
    app.include_router(attachments_api.router)
    return app


async def _seed_auth(settings: Settings, auth_repository: AuthRepository) -> None:
    bootstrap = settings.bootstrap_keys()
    if not bootstrap:
        return
    if isinstance(auth_repository, MemoryAuthRepository):
        for entry in bootstrap:
            auth_repository.add_key(
                entry.key,
                actor_id=entry.actor_id,
                actor_type=entry.actor_type,
                roles=entry.roles,
                caller_id=entry.caller_id,
            )
        return
    seed = getattr(auth_repository, "seed_bootstrap", None)
    if seed is not None:
        await seed(bootstrap)
