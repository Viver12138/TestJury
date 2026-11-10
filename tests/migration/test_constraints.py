"""ACC-M0-004：幂等唯一索引与状态 CHECK 在数据库层真实生效。"""

from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest

from tests.pg import dsn as _dsn


async def _insert_job(
    conn: asyncpg.Connection,
    *,
    idem: str,
    generation: int = 1,
    status: str = "queued",
    superseded_by: str | None = None,
) -> str:
    job_id = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO review_jobs
            (id, case_id, test_type, status, human_status, prompt_version_hash,
             report_schema_version, input_hash, idempotency_key, generation,
             superseded_by, request_payload)
        VALUES ($1::uuid,'TC-1','functional',$2,'pending','hash','report-1.0','ih',$3,$4,$5::uuid,'{}'::jsonb)
        """,
        job_id,
        status,
        idem,
        generation,
        superseded_by,
    )
    return job_id


def test_partial_unique_index_and_checks(migrated_database: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(_dsn())
        try:
            first = await _insert_job(conn, idem="same-key")

            with pytest.raises(asyncpg.UniqueViolationError):
                await _insert_job(conn, idem="same-key")

            # superseded 记录不阻塞新代次：先插入非 active 的第二代，再单向取代
            second = await _insert_job(
                conn, idem="same-key", generation=2, superseded_by=first
            )
            await conn.execute(
                "UPDATE review_jobs SET superseded_by=$1::uuid WHERE id=$2::uuid",
                second,
                first,
            )
            await _insert_job(conn, idem="same-key", generation=3)

            with pytest.raises(asyncpg.CheckViolationError):
                await _insert_job(conn, idem="bad-status", status="unknown")
            with pytest.raises(asyncpg.CheckViolationError):
                await _insert_job(conn, idem="bad-generation", generation=0)
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "INSERT INTO review_jobs (case_id, test_type, status, human_status, "
                    "prompt_version_hash, report_schema_version, input_hash, idempotency_key, "
                    "request_payload, ai_verdict) VALUES "
                    "('TC-2','performance','queued','pending','h','report-1.0','ih2','k2','{}'::jsonb,'approved')"
                )
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_generation_must_be_positive_and_status_enum(migrated_database: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(_dsn())
        try:
            rows = await conn.fetch(
                "SELECT conname FROM pg_constraint WHERE conrelid='review_jobs'::regclass "
                "AND contype='c'"
            )
            names = {row["conname"] for row in rows}
            assert any("status" in name for name in names)
            assert any("generation" in name for name in names)
            indexes = await conn.fetch(
                "SELECT indexdef FROM pg_indexes WHERE indexname='uq_review_jobs_idempotency'"
            )
            assert indexes and "WHERE (superseded_by IS NULL)" in indexes[0]["indexdef"]
        finally:
            await conn.close()

    asyncio.run(scenario())

