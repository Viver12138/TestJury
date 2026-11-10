"""附件上传/下载（docs/03 §1.3）。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import get_attachment_service, get_principal, get_storage
from app.core.auth import Principal
from app.core.errors import ApiError, ErrorCode
from app.services.attachments import AttachmentService
from app.storage.port import Storage

router = APIRouter(prefix="/v1", tags=["attachments"])


@router.post("/attachments")
async def upload_attachment(
    file: UploadFile = File(...),
    sha256: str | None = Form(default=None),
    principal: Principal = Depends(get_principal),
    service: AttachmentService = Depends(get_attachment_service),
):
    content = await file.read()
    computed = hashlib.sha256(content).hexdigest()
    if sha256 and sha256.strip().lower() != computed:
        raise ApiError(
            ErrorCode.INPUT_INVALID,
            "客户端 sha256 与文件内容不一致",
            field="sha256",
        )
    return await service.save(
        file_name=file.filename or "attachment",
        content=content,
        mime_type=file.content_type or "application/octet-stream",
        uploader_id=principal.actor_id,
    )


@router.get("/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: str,
    principal: Principal = Depends(get_principal),
    storage: Storage = Depends(get_storage),
):
    record = await storage.get_attachment(attachment_id)
    if record is None or record.status != "ready":
        raise ApiError(ErrorCode.NOT_FOUND, "附件不存在或已删除")
    path = Path(record.storage_uri)
    if not path.exists():
        raise ApiError(ErrorCode.NOT_FOUND, "附件文件不存在")
    return FileResponse(path, media_type=record.mime_type, filename=record.file_name)
