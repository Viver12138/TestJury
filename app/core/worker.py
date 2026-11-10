"""Worker：领取任务、执行流水线、写终稿（docs/13 §5）。

- 领取用持久化队列语义（内存适配器用锁模拟，PG 用 FOR UPDATE SKIP LOCKED）；
- 终稿写入带 fencing token，旧 Worker 写入被拒绝；
- 执行失败按 `max_attempts` 置 retrying/failed，已完成阶段保留。
"""

from __future__ import annotations

import asyncio
import uuid

import structlog

from app.config import Settings
from app.core.observability import REVIEW_JOBS, RUNNING_JOBS
from app.core.state_machine import FencingMismatch
from app.core.versioning import Versions
from app.pipeline.orchestrator import ReviewPipeline, create_review_tasks_after_report
from app.pipeline.projection import records_from_report
from app.storage.models import ReviewJob, now
from app.storage.port import Storage

logger = structlog.get_logger("testjury.worker")


class Worker:
    def __init__(
        self,
        storage: Storage,
        settings: Settings,
        versions: Versions,
        pipeline: ReviewPipeline,
        *,
        worker_id: str | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.versions = versions
        self.pipeline = pipeline
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def claim_next(self) -> ReviewJob | None:
        return await self.storage.claim_next_job(
            worker_id=self.worker_id, lease_seconds=self.settings.queue_lease_seconds
        )

    async def execute(self, job: ReviewJob) -> str:
        """执行一份已领取的任务；返回终态。"""

        RUNNING_JOBS.inc()
        try:
            return await self._execute(job)
        finally:
            RUNNING_JOBS.dec()

    async def _execute(self, job: ReviewJob) -> str:
        try:
            result = await self.pipeline.run(job, self.versions)
        except FencingMismatch:
            logger.warning("fencing_lost", review_id=job.id, worker=self.worker_id)
            return "fenced_out"
        except Exception as exc:  # pragma: no cover - 失败路径需要 DB 集成测试
            logger.exception("pipeline_failed", review_id=job.id)
            await self.storage.release_job(
                job.id, fencing_token=job.fencing_token, error=str(exc)
            )
            return "failed_or_retrying"

        report = result.report
        if report.get("status") == "failed":
            await self.storage.update_job(
                job.id,
                fencing_token=job.fencing_token,
                status="failed",
                error="preprocess_failed",
                finished_at=now(),
                report_json=None,
            )
            return "failed"

        completeness = report.get("review_completeness") or {}
        warnings = {"model_missing", "budget_exceeded"}
        reasons = set(report.get("degraded_reasons") or [])
        status = (
            "completed_with_warnings"
            if (reasons & warnings) or completeness.get("complete") is False
            else "done"
        )
        report["status"] = status
        report["finished_at"] = now().isoformat()
        report["decision_summary"] = {
            "human_status": job.human_status,
            "latest_decision": None,
            "history_count": 0,
        }
        summary = report.get("summary") or {}
        issue_records = records_from_report(job.id, report)

        await self.storage.finalize_report(
            job.id,
            fencing_token=job.fencing_token,
            fields={
                "status": status,
                "stage": "render",
                "ai_verdict": report.get("ai_verdict"),
                "report_json": report,
                "report_summary": summary,
                "review_completeness": completeness,
                "degraded": bool(report.get("degraded")),
                "degraded_reasons": list(report.get("degraded_reasons") or []),
                "input_quality": report.get("input_quality"),
                "normalized_case": report.get("appendix", {}).get("normalized_case"),
                "report_locked_at": now(),
                "finished_at": now(),
            },
            issues=issue_records,
        )
        await create_review_tasks_after_report(self.storage, job.id, report)
        REVIEW_JOBS.labels(status=status).inc()
        return status

    async def run_once(self) -> str | None:
        job = await self.claim_next()
        if job is None:
            return None
        return await self.execute(job)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                result = await self.run_once()
                if result is None:
                    await asyncio.sleep(self.settings.queue_poll_interval_ms / 1000)
            except asyncio.CancelledError:  # pragma: no cover
                break
            except Exception:  # pragma: no cover
                logger.exception("worker_loop_error")
                await asyncio.sleep(1)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
