"""批量评审（docs/03 §4）：批量只是多个独立单条评审的聚合。

- 批次幂等：重复提交未 force 返回原批次（200）；
- 任一条 test_type 不合法 → 整批 422，不创建批次；
- 批次状态汇总不掩盖单条状态；不做跨用例覆盖率/重复性分析。
"""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.core.auth import Principal
from app.core.errors import ApiError, ErrorCode
from app.core.idempotency import compute_idempotency_key, compute_input_hash
from app.core.versioning import Versions
from app.pipeline.input_check import validate_request
from app.services.reviews import ReviewService
from app.storage.models import BatchRecord, ReviewJob, new_id
from app.storage.port import Storage


class BatchService:
    def __init__(
        self,
        storage: Storage,
        settings: Settings,
        versions: Versions,
        reviews: ReviewService,
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.versions = versions
        self.reviews = reviews

    async def create(self, payload: Any, principal: Principal) -> tuple[int, dict[str, Any]]:
        if not isinstance(payload, dict):
            raise ApiError(ErrorCode.INVALID_JSON, "请求体必须是 JSON 对象")
        cases = payload.get("cases")
        if not isinstance(cases, list) or not cases:
            raise ApiError(ErrorCode.INPUT_INVALID, "cases 必须是非空数组", field="cases")
        if len(cases) > 50:
            raise ApiError(ErrorCode.TOO_MANY_CASES, "单批最多 50 份用例", field="cases")

        options = payload.get("options") or {}
        if not isinstance(options, dict):
            raise ApiError(ErrorCode.INPUT_INVALID, "options 必须是对象", field="options")
        force = bool(options.get("force", False))
        force_all = bool(options.get("force_all", False))

        # 先逐条硬校验：任一条非法则整批拒绝，不创建批次（docs/03 §4）
        normalized_items = []
        hashes = []
        for index, item in enumerate(cases):
            if not isinstance(item, dict):
                raise ApiError(ErrorCode.INVALID_CASE, f"cases[{index}] 必须是对象")
            request = {
                "case": item,
                "options": {"strict_kb": bool(options.get("strict_kb", False))},
            }
            normalized = validate_request(request, self.settings, caller_id=principal.caller_id)
            normalized_items.append((request, normalized))
            hashes.append(
                compute_input_hash(
                    normalized.case,
                    normalized.test_scope,
                    normalized.automation_context,
                    normalized.options,
                )
            )

        batch_key = compute_idempotency_key("|".join(sorted(hashes)), self.versions)
        batch = BatchRecord(
            id=new_id("b-"),
            status="queued",
            total=len(normalized_items),
            caller_id=principal.caller_id or principal.actor_id,
            input_hash="|".join(hashes),
            idempotency_key=batch_key,
        )
        created = await self.storage.create_batch(batch)
        existing_batch = created.id != batch.id
        if existing_batch:
            children = await self.storage.list_jobs(batch_id=created.id, limit=500)
            if not force:
                return 200, self._summary(created, children)
            targets = [
                child
                for child in children
                if force_all or child.status in ("failed", "cancelled")
            ]
            for child in targets:
                request = dict(child.request_payload)
                request["options"] = {**(request.get("options") or {}), "force": True}
                result = await self.reviews.submit(request, principal)
                new_job = await self.storage.get_job(result.body["review_id"])
                if new_job is not None and new_job.id != child.id:
                    await self.storage.update_job(new_job.id, batch_id=created.id)
            await self._refresh_batch(created.id)
            return 202, {
                "batch_id": created.id,
                "total": created.total,
                "poll_url": f"/v1/review-batches/{created.id}",
            }

        for request, _normalized in normalized_items:
            result = await self.reviews.submit(request, principal)
            review_id = result.body["review_id"]
            job = await self.storage.get_job(review_id)
            if job is None:  # pragma: no cover
                continue
            await self.storage.update_job(job.id, batch_id=created.id)

        await self._refresh_batch(created.id)
        return 202, {
            "batch_id": created.id,
            "total": created.total,
            "poll_url": f"/v1/review-batches/{created.id}",
        }

    async def get(self, batch_id: str) -> dict[str, Any]:
        batch = await self.storage.get_batch(batch_id)
        if batch is None:
            raise ApiError(ErrorCode.NOT_FOUND, "批次不存在")
        jobs = await self.storage.list_jobs(batch_id=batch_id, limit=500)
        return self._summary(batch, jobs)

    async def _refresh_batch(self, batch_id: str) -> None:
        batch = await self.storage.get_batch(batch_id)
        if batch is None:
            return
        jobs = await self.storage.list_jobs(batch_id=batch_id, limit=500)
        done = sum(1 for job in jobs if job.status in ("done", "completed_with_warnings"))
        failed = sum(1 for job in jobs if job.status == "failed")
        running = any(job.status in ("queued", "processing", "retrying") for job in jobs)
        if running:
            status = "processing"
        elif jobs and failed == len(jobs):
            status = "failed"
        elif failed:
            status = "partially_completed"
        elif len(jobs) == batch.total:
            status = "completed"
        else:
            status = "processing"
        await self.storage.update_batch(batch_id, status=status, done=done, failed=failed)

    def _summary(self, batch: BatchRecord, jobs: list[ReviewJob] | None = None) -> dict[str, Any]:
        jobs = jobs or []
        done = sum(1 for job in jobs if job.status in ("done", "completed_with_warnings"))
        failed = sum(1 for job in jobs if job.status == "failed")
        queued = sum(1 for job in jobs if job.status in ("queued", "processing", "retrying"))
        status = batch.status
        if jobs:
            if queued:
                status = "processing"
            elif failed == len(jobs):
                status = "failed"
            elif failed:
                status = "partially_completed"
            elif done == len(jobs):
                status = "completed"
        verdict_distribution: dict[str, int] = {}
        human_distribution: dict[str, int] = {}
        modules: dict[str, int] = {}
        for job in jobs:
            if job.ai_verdict:
                verdict_distribution[job.ai_verdict] = verdict_distribution.get(job.ai_verdict, 0) + 1
            human_distribution[job.human_status] = human_distribution.get(job.human_status, 0) + 1
            if job.report_summary and job.report_summary.get("blocker"):
                modules[job.module or "-"] = (
                    modules.get(job.module or "-", 0) + job.report_summary["blocker"]
                )
        return {
            "batch_id": batch.id,
            "status": status,
            "total": batch.total,
            "done": done,
            "failed": failed,
            "queued": queued,
            "items": [
                {
                    "case_id": job.case_id,
                    "review_id": job.id,
                    "status": job.status,
                    "ai_verdict": job.ai_verdict,
                    "human_status": job.human_status,
                }
                for job in jobs
            ],
            "overview": {
                "ai_verdict_distribution": verdict_distribution,
                "human_status_distribution": human_distribution,
                "hot_modules": [
                    {"module": module, "blocker": count}
                    for module, count in sorted(modules.items(), key=lambda item: -item[1])
                ],
            },
        }
