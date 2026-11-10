"""ACC-M0-019：fencing token 双 Worker 写入保护（真实 PostgreSQL）。"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.core.state_machine import FencingMismatch
from app.storage.models import ReviewJob, now
from app.storage.postgres import PostgresStorage
from tests.pg import dsn as _dsn


def _job() -> ReviewJob:
    return ReviewJob(
        id=str(uuid.uuid4()),
        case_id="TC-FENCE-1",
        case_version=1,
        module="挖宝",
        test_type="functional",
        test_type_source="request",
        status="queued",
        stage=None,
        input_hash="input-hash",
        idempotency_key=f"key-{uuid.uuid4()}",
        request_payload={"case": {"case_id": "TC-FENCE-1"}},
        report_schema_version="report-1.0",
        prompt_version_hash="prompt-hash",
        created_at=now(),
    )


def test_fencing_token_rejects_stale_worker(migrated_database: str) -> None:
    async def scenario() -> None:
        storage = PostgresStorage(_dsn())
        try:
            job = _job()
            outcome = await storage.submit_review(job, force=False)
            assert outcome.kind == "created"

            worker_a = await storage.claim_next_job(worker_id="worker-a", lease_seconds=0)
            assert worker_a is not None and worker_a.fencing_token == 1

            worker_b = await storage.claim_next_job(worker_id="worker-b", lease_seconds=60)
            assert worker_b is not None and worker_b.fencing_token == 2

            with pytest.raises(FencingMismatch):
                await storage.update_job(
                    job.id,
                    fencing_token=worker_a.fencing_token,
                    status="done",
                    report_json={"review_id": job.id, "status": "done"},
                    report_locked_at=now(),
                )

            updated = await storage.update_job(
                job.id,
                fencing_token=worker_b.fencing_token,
                status="done",
                report_json={"review_id": job.id, "status": "done"},
                report_locked_at=now(),
            )
            assert updated.status == "done"
            assert updated.fencing_token == 2

            with pytest.raises(FencingMismatch):
                await storage.update_job(
                    job.id,
                    fencing_token=worker_a.fencing_token,
                    report_json={"tampered": True},
                )
        finally:
            await storage.close()

    asyncio.run(scenario())


def test_locked_report_cannot_be_updated(migrated_database: str) -> None:
    async def scenario() -> None:
        storage = PostgresStorage(_dsn())
        try:
            job = _job()
            await storage.submit_review(job, force=False)
            worker = await storage.claim_next_job(worker_id="w", lease_seconds=60)
            assert worker is not None
            await storage.update_job(
                job.id,
                fencing_token=worker.fencing_token,
                status="done",
                report_json={"review_id": job.id, "status": "done"},
                report_locked_at=now(),
            )
            with pytest.raises(Exception) as excinfo:
                await storage.update_job(job.id, report_json={"changed": True})
            assert "report_locked" in str(excinfo.value)
        finally:
            await storage.close()

    asyncio.run(scenario())

