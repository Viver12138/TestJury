"""附件（v1 本机卷 + 内容寻址，docs/03 §1.3）。

- 同 sha256 重复上传返回同一 attachment_id，不重复存储；
- 只接受白名单 MIME 与大小上限；
- v1 不把附件内容发送给模型，报告 `analyzed_by_ai=false`。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.storage.models import AttachmentRecord
from app.storage.port import Storage

_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
}


class AttachmentService:
    def __init__(self, storage: Storage, settings: Settings) -> None:
        self.storage = storage
        self.settings = settings

    async def save(
        self,
        *,
        file_name: str,
        content: bytes,
        mime_type: str,
        uploader_id: str | None,
    ) -> dict[str, object]:
        if mime_type not in self.settings.allowed_mime_types:
            raise ApiError(
                ErrorCode.INPUT_INVALID,
                f"不支持的附件类型: {mime_type}",
                field="file",
            )
        limit = self.settings.attachment_max_mb * 1024 * 1024
        if len(content) > limit:
            raise ApiError(ErrorCode.INPUT_INVALID, "附件超过大小上限", field="file")

        digest = hashlib.sha256(content).hexdigest()
        existing = await self.storage.get_attachment(f"a-{digest[:12]}")
        if existing is not None and existing.status == "ready":
            return self._public(existing)

        root = Path(self.settings.attachment_dir)
        target_dir = root / digest[:2]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{digest}{_EXTENSIONS.get(mime_type, '.bin')}"
        if not target.exists():
            target.write_bytes(content)

        record = AttachmentRecord(
            id=f"a-{digest[:12]}",
            file_name=file_name,
            mime_type=mime_type,
            size_bytes=len(content),
            sha256=digest,
            storage_uri=str(target),
            storage_path=str(target.relative_to(root)) if target.is_relative_to(root) else str(target),
            uploader_id=uploader_id,
        )
        stored = await self.storage.add_attachment(record)
        return self._public(stored)

    @staticmethod
    def _public(record: AttachmentRecord) -> dict[str, object]:
        return {
            "attachment_id": record.id,
            "file_name": record.file_name,
            "sha256": record.sha256,
            "size_bytes": record.size_bytes,
            "status": record.status,
            "analyzed_by_ai": False,
        }
