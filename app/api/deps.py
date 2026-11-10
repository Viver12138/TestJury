"""API 依赖：从 app.state 取服务与存储，避免全局单例阻碍测试隔离。"""

from __future__ import annotations

from fastapi import Request

from app.core.auth import Principal, get_principal
from app.services.attachments import AttachmentService
from app.services.batches import BatchService
from app.services.decisions import DecisionService
from app.services.reviews import ReviewService
from app.services.tasks import ReviewTaskService
from app.storage.port import Storage


def get_storage(request: Request) -> Storage:
    return request.app.state.storage


def get_review_service(request: Request) -> ReviewService:
    return request.app.state.review_service


def get_batch_service(request: Request) -> BatchService:
    return request.app.state.batch_service


def get_decision_service(request: Request) -> DecisionService:
    return request.app.state.decision_service


def get_task_service(request: Request) -> ReviewTaskService:
    return request.app.state.task_service


def get_attachment_service(request: Request) -> AttachmentService:
    return request.app.state.attachment_service


__all__ = [
    "Principal",
    "get_principal",
    "get_storage",
    "get_review_service",
    "get_batch_service",
    "get_decision_service",
    "get_task_service",
    "get_attachment_service",
]
