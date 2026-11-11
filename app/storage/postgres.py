"""PostgreSQL 存储适配器（asyncpg 直连，语义与内存实现一致）。

关键并发点：
- `submit_review` 用事务级 advisory lock 按 idempotency_key 串行化；
- `claim_next_job` 用 FOR UPDATE SKIP LOCKED 领取，fencing_token 仅在领取/接管时递增；
- 所有带令牌的写入都在 SQL 条件中校验，旧 Worker 的 UPDATE 影响 0 行即失败。
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.core.errors import ApiError, ErrorCode
from app.core.state_machine import FencingMismatch, is_terminal_review_status
from app.storage.models import (
    AttachmentRecord,
    AuditRecord,
    BatchRecord,
    CandidateRecord,
    DecisionRecord,
    IssueRecord,
    ModelRunRecord,
    ReviewJob,
    ReviewTaskRecord,
    StageAttempt,
    StageRecord,
    VoteRecord,
)
from app.storage.port import SubmitOutcome

_JSONB_CODECS = ("json", "jsonb")


def _normalize_dsn(dsn: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://"):
        if dsn.startswith(prefix):
            return "postgresql://" + dsn[len(prefix) :]
    return dsn


async def _init_connection(conn: asyncpg.Connection) -> None:
    for type_name in _JSONB_CODECS:
        await conn.set_type_codec(
            type_name,
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )


class _PooledStorage:
    def __init__(self, dsn: str) -> None:
        self._dsn = _normalize_dsn(dsn)
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._dsn, min_size=1, max_size=8, init=_init_connection
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


class PostgresAuthRepository(_PooledStorage):
    async def find_by_hash(self, key_hash: str):
        from app.core.auth import ApiKeyRecord

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM api_keys WHERE key_hash = $1", key_hash)
        if row is None:
            return None
        return ApiKeyRecord(
            key_hash=row["key_hash"],
            actor_id=row["actor_id"],
            actor_type=row["actor_type"],
            roles=frozenset(row["roles"] or []),
            caller_id=row["caller_id"],
            revoked_at=row["revoked_at"],
            expires_at=row["expires_at"],
        )

    async def seed_bootstrap(self, entries) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            for entry in entries:
                from app.core.auth import hash_api_key

                await conn.execute(
                    """
                    INSERT INTO api_keys (key_hash, actor_id, actor_type, roles, caller_id)
                    VALUES ($1,$2,$3,$4,$5)
                    ON CONFLICT (key_hash) DO NOTHING
                    """,
                    hash_api_key(entry.key),
                    entry.actor_id,
                    entry.actor_type,
                    entry.roles,
                    entry.caller_id,
                )


_JOB_COLUMNS = (
    "id",
    "batch_id",
    "case_id",
    "case_title",
    "case_version",
    "module",
    "test_type",
    "test_type_source",
    "status",
    "stage",
    "ai_verdict",
    "human_status",
    "current_decision_id",
    "degraded",
    "degraded_reasons",
    "participants",
    "topology",
    "topology_snapshot",
    "review_completeness",
    "input_quality",
    "timings",
    "test_scope",
    "automation_context",
    "kb_content_version",
    "kb_build_version",
    "rubric_version",
    "prompt_versions",
    "prompt_version_hash",
    "retrieval_config_version",
    "embedding_profile_id",
    "reranker_profile_id",
    "model_config_version",
    "report_schema_version",
    "input_hash",
    "idempotency_key",
    "generation",
    "parent_review_id",
    "superseded_by",
    "request_payload",
    "normalized_case",
    "report_summary",
    "report_json",
    "report_locked_at",
    "total_cost_estimate",
    "cost_currency",
    "error",
    "attempt_count",
    "max_attempts",
    "locked_by",
    "locked_at",
    "lease_expires_at",
    "fencing_token",
    "last_error",
    "submitter_id",
    "created_at",
    "started_at",
    "finished_at",
)

_JOB_JSON_FIELDS = {
    "degraded_reasons",
    "participants",
    "topology_snapshot",
    "review_completeness",
    "input_quality",
    "timings",
    "test_scope",
    "automation_context",
    "prompt_versions",
    "request_payload",
    "normalized_case",
    "report_summary",
    "report_json",
}


def _as_uuid(value: str | None) -> str | None:
    return str(value) if value else None


def _row_to_job(row: asyncpg.Record) -> ReviewJob:
    data = dict(row)
    return ReviewJob(
        id=str(data["id"]),
        case_id=data["case_id"],
        case_version=data["case_version"],
        module=data["module"],
        test_type=data["test_type"],
        test_type_source=data["test_type_source"],
        status=data["status"],
        stage=data["stage"],
        input_hash=data["input_hash"],
        idempotency_key=data["idempotency_key"],
        request_payload=data["request_payload"] or {},
        report_schema_version=data["report_schema_version"],
        generation=data["generation"],
        parent_review_id=_as_uuid(data["parent_review_id"]),
        superseded_by=_as_uuid(data["superseded_by"]),
        batch_id=_as_uuid(data["batch_id"]),
        case_title=data["case_title"],
        ai_verdict=data["ai_verdict"],
        human_status=data["human_status"],
        current_decision_id=data["current_decision_id"],
        degraded=data["degraded"],
        degraded_reasons=data["degraded_reasons"] or [],
        participants=data["participants"] or [],
        topology=data["topology"],
        topology_snapshot=data["topology_snapshot"] or {},
        review_completeness=data["review_completeness"] or {},
        input_quality=data["input_quality"] or {},
        timings=data["timings"] or {},
        test_scope=data["test_scope"],
        automation_context=data["automation_context"],
        kb_content_version=data["kb_content_version"],
        kb_build_version=data["kb_build_version"],
        rubric_version=data["rubric_version"],
        prompt_versions=data["prompt_versions"] or {},
        prompt_version_hash=data["prompt_version_hash"],
        retrieval_config_version=data["retrieval_config_version"],
        embedding_profile_id=data["embedding_profile_id"],
        reranker_profile_id=data["reranker_profile_id"],
        model_config_version=data["model_config_version"],
        normalized_case=data["normalized_case"],
        report_summary=data["report_summary"],
        report_json=data["report_json"],
        report_locked_at=data["report_locked_at"],
        total_cost_estimate=float(data["total_cost_estimate"]) if data["total_cost_estimate"] is not None else None,
        cost_currency=data["cost_currency"] or "CNY",
        error=data["error"],
        attempt_count=data["attempt_count"],
        max_attempts=data["max_attempts"],
        locked_by=data["locked_by"],
        locked_at=data["locked_at"],
        lease_expires_at=data["lease_expires_at"],
        fencing_token=data["fencing_token"],
        last_error=data["last_error"],
        submitter_id=data["submitter_id"],
        created_at=data["created_at"],
        started_at=data["started_at"],
        finished_at=data["finished_at"],
    )


class PostgresStorage(_PooledStorage):
    # ── 基础 ──

    async def ping(self) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval("SELECT 1") == 1

    async def migration_version(self) -> str | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            try:
                return await conn.fetchval("SELECT version_num FROM alembic_version")
            except asyncpg.UndefinedTableError:
                return None

    # ── 提交与任务 ──

    async def submit_review(self, job: ReviewJob, *, force: bool) -> SubmitOutcome:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1))", job.idempotency_key
                )
                active = await conn.fetchrow(
                    "SELECT * FROM review_jobs WHERE idempotency_key = $1 "
                    "AND superseded_by IS NULL ORDER BY generation DESC LIMIT 1",
                    job.idempotency_key,
                )
                if active is not None:
                    existing = _row_to_job(active)
                    if existing.input_hash != job.input_hash:
                        return SubmitOutcome(kind="conflict", job=existing)
                    if not force:
                        return SubmitOutcome(kind="replay", job=existing)
                    if not is_terminal_review_status(existing.status):
                        return SubmitOutcome(kind="in_progress", job=existing)

                    generation = await conn.fetchval(
                        "SELECT COALESCE(MAX(generation),0)+1 FROM review_jobs "
                        "WHERE idempotency_key=$1",
                        job.idempotency_key,
                    )
                    job = replace(
                        job, generation=int(generation), parent_review_id=existing.id
                    )
                    await conn.execute(
                        "UPDATE review_jobs SET superseded_by=$1 WHERE id=$2",
                        UUID(job.id),
                        UUID(existing.id),
                    )
                elif force:
                    generation = await conn.fetchval(
                        "SELECT COALESCE(MAX(generation),0)+1 FROM review_jobs "
                        "WHERE idempotency_key=$1",
                        job.idempotency_key,
                    )
                    job = replace(job, generation=int(generation))

                await self._insert_job(conn, job)
                return SubmitOutcome(kind="created", job=job)

    async def _insert_job(self, conn: asyncpg.Connection, job: ReviewJob) -> None:
        values = {
            "id": UUID(job.id),
            "batch_id": UUID(job.batch_id) if job.batch_id else None,
            "case_id": job.case_id,
            "case_title": job.case_title,
            "case_version": job.case_version,
            "module": job.module,
            "test_type": job.test_type,
            "test_type_source": job.test_type_source,
            "status": job.status,
            "stage": job.stage,
            "ai_verdict": job.ai_verdict,
            "human_status": job.human_status,
            "current_decision_id": job.current_decision_id,
            "degraded": job.degraded,
            "degraded_reasons": job.degraded_reasons,
            "participants": job.participants,
            "topology": job.topology,
            "topology_snapshot": job.topology_snapshot,
            "review_completeness": job.review_completeness,
            "input_quality": job.input_quality,
            "timings": job.timings,
            "test_scope": job.test_scope,
            "automation_context": job.automation_context,
            "kb_content_version": job.kb_content_version,
            "kb_build_version": job.kb_build_version,
            "rubric_version": job.rubric_version,
            "prompt_versions": job.prompt_versions,
            "prompt_version_hash": job.prompt_version_hash,
            "retrieval_config_version": job.retrieval_config_version,
            "embedding_profile_id": job.embedding_profile_id,
            "reranker_profile_id": job.reranker_profile_id,
            "model_config_version": job.model_config_version,
            "report_schema_version": job.report_schema_version,
            "input_hash": job.input_hash,
            "idempotency_key": job.idempotency_key,
            "generation": job.generation,
            "parent_review_id": UUID(job.parent_review_id) if job.parent_review_id else None,
            "superseded_by": None,
            "request_payload": job.request_payload,
            "normalized_case": job.normalized_case,
            "report_summary": job.report_summary,
            "report_json": job.report_json,
            "report_locked_at": job.report_locked_at,
            "error": job.error,
            "attempt_count": job.attempt_count,
            "max_attempts": job.max_attempts,
            "locked_by": job.locked_by,
            "locked_at": job.locked_at,
            "lease_expires_at": job.lease_expires_at,
            "fencing_token": job.fencing_token,
            "last_error": job.last_error,
            "submitter_id": job.submitter_id,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }
        columns = ", ".join(values)
        placeholders = ", ".join(f"${index}" for index in range(1, len(values) + 1))
        await conn.execute(
            f"INSERT INTO review_jobs ({columns}) VALUES ({placeholders})",
            *values.values(),
        )

    async def get_job(self, review_id: str) -> ReviewJob | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM review_jobs WHERE id=$1::uuid", review_id)
        return _row_to_job(row) if row else None

    async def delete_job(self, review_id: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM review_jobs WHERE id=$1::uuid", review_id)
        if result.endswith(" 0"):
            raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")

    async def list_jobs(
        self,
        *,
        case_id: str | None = None,
        batch_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReviewJob]:
        clauses = []
        params: list[Any] = []
        if case_id:
            params.append(case_id)
            clauses.append(f"case_id = ${len(params)}")
        if batch_id:
            params.append(UUID(batch_id))
            clauses.append(f"batch_id = ${len(params)}")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        sql = (
            f"SELECT * FROM review_jobs {where} ORDER BY created_at DESC "
            f"LIMIT ${len(params) - 1} OFFSET ${len(params)}"
        )
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [_row_to_job(row) for row in rows]

    async def update_job(
        self, review_id: str, *, fencing_token: int | None = None, **fields: Any
    ) -> ReviewJob:
        if fields:
            values: list[Any] = []
            assignments: list[str] = []
            for key, value in fields.items():
                if key not in _JOB_COLUMNS:
                    raise ValueError(f"不可更新字段: {key}")
                values.append(UUID(value) if key in ("parent_review_id", "superseded_by", "batch_id") and value else value)
                assignments.append(f"{key} = ${len(values)}")
            values.append(UUID(review_id))
            where = f"id = ${len(values)}"
            if fencing_token is not None:
                values.append(fencing_token)
                where += f" AND fencing_token = ${len(values)}"
            sql = (
                f"UPDATE review_jobs SET {', '.join(assignments)} WHERE {where} RETURNING *"
            )
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(sql, *values)
        else:
            return (await self.get_job(review_id)) or self._missing()

        if row is None:
            current = await self.get_job(review_id)
            if current is None:
                raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")
            raise FencingMismatch(fencing_token if fencing_token is not None else -1, current.fencing_token)
        return _row_to_job(row)

    @staticmethod
    def _missing() -> ReviewJob:
        raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")

    async def claim_next_job(
        self, *, worker_id: str, lease_seconds: int
    ) -> ReviewJob | None:
        pool = await self._get_pool()
        sql = """
            WITH candidate AS (
                SELECT id FROM review_jobs
                WHERE status IN ('queued','retrying')
                   OR (status = 'processing' AND lease_expires_at IS NOT NULL AND lease_expires_at <= now())
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE review_jobs AS jobs
            SET status = 'processing',
                stage = COALESCE(jobs.stage, 'input_check'),
                attempt_count = jobs.attempt_count + 1,
                locked_by = $1,
                locked_at = now(),
                lease_expires_at = now() + make_interval(secs => $2),
                fencing_token = jobs.fencing_token + 1,
                started_at = COALESCE(jobs.started_at, now())
            FROM candidate
            WHERE jobs.id = candidate.id
            RETURNING jobs.*
        """
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, worker_id, lease_seconds)
        return _row_to_job(row) if row else None

    async def heartbeat(
        self, review_id: str, *, fencing_token: int, lease_seconds: int
    ) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE review_jobs SET lease_expires_at = now() + make_interval(secs => $1) "
                "WHERE id = $2::uuid AND fencing_token = $3 RETURNING id",
                lease_seconds,
                review_id,
                fencing_token,
            )
        return row is not None

    async def release_job(
        self, review_id: str, *, fencing_token: int, error: str
    ) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT attempt_count, max_attempts FROM review_jobs WHERE id=$1::uuid FOR UPDATE",
                    review_id,
                )
                if row is None:
                    raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")
                status = "failed" if row["attempt_count"] >= row["max_attempts"] else "retrying"
                result = await conn.execute(
                    "UPDATE review_jobs SET status=$1, last_error=$2, error=$3, "
                    "finished_at=CASE WHEN $1='failed' THEN now() ELSE NULL END, "
                    "lease_expires_at=NULL, locked_by=NULL "
                    "WHERE id=$4::uuid AND fencing_token=$5",
                    status,
                    error,
                    error if status == "failed" else None,
                    review_id,
                    fencing_token,
                )
                if result.endswith(" 0"):
                    raise FencingMismatch(fencing_token, -1)

    async def queue_depth(self) -> int:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            return int(
                await conn.fetchval(
                    "SELECT count(*) FROM review_jobs WHERE status IN ('queued','retrying')"
                )
            )

    # ── 阶段 ──

    async def upsert_stage(self, stage: StageRecord) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO review_stages
                    (review_id, stage, status, attempt, fencing_token, input_digest,
                     output_ref, started_at, finished_at, error)
                VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (review_id, stage) DO UPDATE SET
                    status=EXCLUDED.status,
                    attempt=EXCLUDED.attempt,
                    fencing_token=EXCLUDED.fencing_token,
                    input_digest=EXCLUDED.input_digest,
                    output_ref=EXCLUDED.output_ref,
                    started_at=COALESCE(EXCLUDED.started_at, review_stages.started_at),
                    finished_at=EXCLUDED.finished_at,
                    error=EXCLUDED.error
                """,
                UUID(stage.review_id),
                stage.stage,
                stage.status,
                stage.attempt,
                stage.fencing_token,
                stage.input_digest,
                stage.output_ref,
                stage.started_at,
                stage.finished_at,
                stage.error,
            )

    async def list_stages(self, review_id: str) -> list[StageRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM review_stages WHERE review_id=$1::uuid", review_id
            )
        return [
            StageRecord(
                review_id=str(row["review_id"]),
                stage=row["stage"],
                status=row["status"],
                attempt=row["attempt"],
                fencing_token=row["fencing_token"],
                input_digest=row["input_digest"],
                output_ref=row["output_ref"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                error=row["error"],
            )
            for row in rows
        ]

    async def add_stage_attempt(self, attempt: StageAttempt) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO review_stage_attempts
                    (review_id, stage, attempt_no, fencing_token, status, input_digest,
                     output_ref, started_at, finished_at, error_code, error_message,
                     worker_id, model_run_id)
                VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                ON CONFLICT (review_id, stage, attempt_no) DO NOTHING
                """,
                UUID(attempt.review_id),
                attempt.stage,
                attempt.attempt_no,
                attempt.fencing_token,
                attempt.status,
                attempt.input_digest,
                attempt.output_ref,
                attempt.started_at,
                attempt.finished_at,
                attempt.error_code,
                attempt.error_message,
                attempt.worker_id,
                UUID(attempt.model_run_id) if attempt.model_run_id else None,
            )

    async def list_stage_attempts(self, review_id: str) -> list[StageAttempt]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM review_stage_attempts WHERE review_id=$1::uuid "
                "ORDER BY stage, attempt_no",
                review_id,
            )
        return [
            StageAttempt(
                review_id=str(row["review_id"]),
                stage=row["stage"],
                attempt_no=row["attempt_no"],
                status=row["status"],
                fencing_token=row["fencing_token"],
                input_digest=row["input_digest"],
                output_ref=row["output_ref"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                worker_id=row["worker_id"],
                model_run_id=str(row["model_run_id"]) if row["model_run_id"] else None,
            )
            for row in rows
        ]

    # ── 候选与投票 ──

    async def replace_candidates(
        self, review_id: str, candidates: list[CandidateRecord]
    ) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # 重试会重新融合：先清理旧投票，否则候选删除会触发 FK
                await conn.execute(
                    "DELETE FROM issue_votes WHERE review_id=$1::uuid", review_id
                )
                await conn.execute(
                    "DELETE FROM review_candidates WHERE review_id=$1::uuid", review_id
                )
                for candidate in candidates:
                    await conn.execute(
                        """
                        INSERT INTO review_candidates
                            (id, review_id, candidate_no, step_index, dimension,
                             severity_proposal, standardized_text, claims, evidence_status,
                             vote_valid_count, vote_completeness, evidence_refs, proposed_by,
                             merged_from, fusion_basis, status, category,
                             kb_grounded, kb_refs, evidence_type, evidence_strength,
                             evidence_quote, model_evidence_status, evidence_support_status,
                             validation_status, parse_warnings, model_confidence, suggestion)
                        VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,
                                $18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28)
                        """,
                        UUID(candidate.id),
                        UUID(review_id),
                        candidate.candidate_no,
                        candidate.step_index,
                        candidate.dimension,
                        candidate.severity_proposal,
                        candidate.standardized_text,
                        candidate.claims,
                        candidate.evidence_status,
                        candidate.vote_valid_count,
                        candidate.vote_completeness,
                        candidate.evidence_refs,
                        candidate.proposed_by,
                        candidate.merged_from,
                        candidate.fusion_basis,
                        candidate.status,
                        candidate.category,
                        candidate.kb_grounded,
                        candidate.kb_refs,
                        candidate.evidence_type,
                        candidate.evidence_strength,
                        candidate.evidence_quote,
                        candidate.model_evidence_status,
                        candidate.evidence_support_status,
                        candidate.validation_status,
                        candidate.parse_warnings,
                        candidate.model_confidence,
                        candidate.suggestion,
                    )

    async def list_candidates(self, review_id: str) -> list[CandidateRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM review_candidates WHERE review_id=$1::uuid ORDER BY candidate_no",
                review_id,
            )
        return [
            CandidateRecord(
                id=str(row["id"]),
                review_id=str(row["review_id"]),
                candidate_no=row["candidate_no"],
                dimension=row["dimension"],
                standardized_text=row["standardized_text"],
                step_index=row["step_index"],
                severity_proposal=row["severity_proposal"],
                claims=row["claims"] or [],
                evidence_status=row["evidence_status"],
                evidence_refs=row["evidence_refs"] or [],
                kb_grounded=row["kb_grounded"],
                kb_refs=row["kb_refs"] or [],
                evidence_type=row["evidence_type"],
                evidence_strength=row["evidence_strength"],
                evidence_quote=row["evidence_quote"],
                model_evidence_status=row["model_evidence_status"],
                evidence_support_status=row["evidence_support_status"],
                validation_status=row["validation_status"] or "passed",
                parse_warnings=row["parse_warnings"] or [],
                model_confidence=row["model_confidence"],
                suggestion=row["suggestion"],
                proposed_by=row["proposed_by"] or [],
                merged_from=row["merged_from"] or [],
                fusion_basis=row["fusion_basis"] or {},
                status=row["status"],
                vote_valid_count=row["vote_valid_count"],
                vote_completeness=row["vote_completeness"],
                category=row["category"],
            )
            for row in rows
        ]

    async def add_votes(self, review_id: str, votes: list[VoteRecord]) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            for vote in votes:
                await conn.execute(
                    """
                    INSERT INTO issue_votes
                        (candidate_id, review_id, model_run_id, reviewer_id, validity,
                         severity, reason)
                    VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6,$7)
                    ON CONFLICT (candidate_id, reviewer_id) DO NOTHING
                    """,
                    UUID(vote.candidate_id),
                    UUID(review_id),
                    UUID(vote.model_run_id) if vote.model_run_id else None,
                    vote.reviewer_id,
                    vote.validity,
                    vote.severity,
                    vote.reason,
                )

    async def list_votes(self, review_id: str) -> list[VoteRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM issue_votes WHERE review_id=$1::uuid ORDER BY id", review_id
            )
        return [
            VoteRecord(
                id=str(row["id"]),
                review_id=str(row["review_id"]),
                candidate_id=str(row["candidate_id"]),
                reviewer_id=row["reviewer_id"],
                validity=row["validity"],
                severity=row["severity"],
                reason=row["reason"],
                model_run_id=str(row["model_run_id"]) if row["model_run_id"] else None,
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def add_model_run(self, run: ModelRunRecord) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO model_runs
                    (id, review_id, role, provider, model, requested_model, model_version,
                     prompt_version, attempt, status, request_tokens, response_tokens,
                     latency_ms, raw_request, raw_response, parsed_output, parse_warnings,
                     cost_estimate, cost_currency, price_config_version, error,
                     operation, request_hash, response_hash, error_code,
                     masking_policy_id, masking_policy_version, masking_report)
                VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                        $16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28)
                """,
                UUID(run.id),
                UUID(run.review_id),
                run.role,
                run.provider,
                run.model,
                run.requested_model,
                run.model_version,
                run.prompt_version,
                run.attempt,
                run.status,
                run.request_tokens,
                run.response_tokens,
                run.latency_ms,
                run.raw_request,
                run.raw_response,
                run.parsed_output,
                run.parse_warnings,
                run.cost_estimate,
                run.cost_currency,
                run.price_config_version,
                run.error,
                run.operation,
                run.request_hash,
                run.response_hash,
                run.error_code,
                run.masking_policy_id,
                run.masking_policy_version,
                run.masking_report,
            )

    async def list_model_runs(self, review_id: str) -> list[ModelRunRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM model_runs WHERE review_id=$1::uuid ORDER BY created_at, attempt",
                review_id,
            )
        return [
            ModelRunRecord(
                id=str(row["id"]),
                review_id=str(row["review_id"]),
                role=row["role"],
                provider=row["provider"],
                model=row["model"],
                requested_model=row["requested_model"],
                model_version=row["model_version"],
                prompt_version=row["prompt_version"],
                attempt=row["attempt"],
                status=row["status"],
                request_tokens=row["request_tokens"],
                response_tokens=row["response_tokens"],
                latency_ms=row["latency_ms"],
                raw_request=row["raw_request"],
                raw_response=row["raw_response"],
                parsed_output=row["parsed_output"],
                parse_warnings=row["parse_warnings"] or [],
                cost_estimate=float(row["cost_estimate"]) if row["cost_estimate"] is not None else None,
                cost_currency=row["cost_currency"] or "CNY",
                price_config_version=row["price_config_version"],
                error=row["error"],
                operation=row["operation"] or "blind_review",
                request_hash=row["request_hash"],
                response_hash=row["response_hash"],
                error_code=row["error_code"],
                masking_policy_id=row["masking_policy_id"],
                masking_policy_version=row["masking_policy_version"],
                masking_report=row["masking_report"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    # ── 报告投影与附件绑定 ──

    async def finalize_report(
        self,
        review_id: str,
        *,
        fencing_token: int,
        fields: dict[str, Any],
        issues: list[IssueRecord],
    ) -> ReviewJob:
        values: list[Any] = []
        assignments: list[str] = []
        for key, value in fields.items():
            if key not in _JOB_COLUMNS:
                raise ValueError(f"不可更新字段: {key}")
            values.append(value)
            assignments.append(f"{key} = ${len(values)}")
        values.extend([UUID(review_id), fencing_token])
        sql = (
            f"UPDATE review_jobs SET {', '.join(assignments)} "
            f"WHERE id = ${len(values) - 1}::uuid AND fencing_token = ${len(values)} "
            f"RETURNING *"
        )
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(sql, *values)
                if row is None:
                    current = await conn.fetchrow(
                        "SELECT fencing_token FROM review_jobs WHERE id=$1::uuid",
                        review_id,
                    )
                    if current is None:
                        raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")
                    raise FencingMismatch(fencing_token, current["fencing_token"])
                await conn.execute(
                    "DELETE FROM issues WHERE review_id=$1::uuid", UUID(review_id)
                )
                for issue in issues:
                    await self._insert_issue(conn, issue)
        return _row_to_job(row)

    async def _insert_issue(self, conn: asyncpg.Connection, issue: IssueRecord) -> None:
        await conn.execute(
            """
            INSERT INTO issues
                (id, review_id, candidate_id, issue_no, step_index, dimension, severity,
                 category, evidence_quote, rationale, suggestion, kb_grounded, kb_refs,
                 evidence_refs, evidence_type, evidence_strength, evidence_status,
                 proposed_by, confidence, confidence_source, model_confidence,
                 validation_status, evidence_support_status, decision_status, status,
                 chief_decision, chief_reason, human_verdict)
            VALUES ($1::uuid,$2::uuid,$3::uuid,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,
                    $15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28)
            """,
            UUID(issue.id),
            UUID(issue.review_id),
            UUID(issue.candidate_id) if issue.candidate_id else None,
            issue.issue_no,
            issue.step_index,
            issue.dimension,
            issue.severity,
            issue.category,
            issue.evidence_quote,
            issue.rationale,
            issue.suggestion,
            issue.kb_grounded,
            issue.kb_refs,
            issue.evidence_refs,
            issue.evidence_type,
            issue.evidence_strength,
            issue.evidence_status,
            issue.proposed_by,
            issue.confidence,
            issue.confidence_source,
            issue.model_confidence,
            issue.validation_status,
            issue.evidence_support_status,
            issue.decision_status,
            issue.status,
            issue.chief_decision,
            issue.chief_reason,
            issue.human_verdict,
        )

    async def replace_issues(self, review_id: str, issues: list[IssueRecord]) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM issues WHERE review_id=$1::uuid", UUID(review_id)
                )
                for issue in issues:
                    await self._insert_issue(conn, issue)

    async def list_issues(self, review_id: str) -> list[IssueRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM issues WHERE review_id=$1::uuid ORDER BY issue_no",
                review_id,
            )
        return [
            IssueRecord(
                id=str(row["id"]),
                review_id=str(row["review_id"]),
                issue_no=row["issue_no"],
                candidate_id=str(row["candidate_id"]) if row["candidate_id"] else None,
                step_index=row["step_index"],
                dimension=row["dimension"],
                severity=row["severity"],
                category=row["category"],
                evidence_quote=row["evidence_quote"],
                rationale=row["rationale"],
                suggestion=row["suggestion"],
                status=row["status"],
                kb_grounded=row["kb_grounded"],
                kb_refs=row["kb_refs"] or [],
                evidence_refs=row["evidence_refs"] or [],
                evidence_type=row["evidence_type"],
                evidence_strength=row["evidence_strength"],
                evidence_status=row["evidence_status"],
                proposed_by=row["proposed_by"] or [],
                confidence=float(row["confidence"]) if row["confidence"] is not None else None,
                confidence_source=row["confidence_source"],
                model_confidence=float(row["model_confidence"])
                if row["model_confidence"] is not None
                else None,
                validation_status=row["validation_status"],
                evidence_support_status=row["evidence_support_status"],
                decision_status=row["decision_status"],
                chief_decision=row["chief_decision"],
                chief_reason=row["chief_reason"],
                human_verdict=row["human_verdict"],
            )
            for row in rows
        ]

    async def bind_review_attachments(
        self, review_id: str, attachments: list[AttachmentRecord]
    ) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            for attachment in attachments:
                await conn.execute(
                    """
                    INSERT INTO review_attachments
                        (review_id, attachment_id, file_name, sha256, status)
                    VALUES ($1::uuid,$2::uuid,$3,$4,$5)
                    ON CONFLICT (review_id, attachment_id) DO NOTHING
                    """,
                    UUID(review_id),
                    UUID(attachment.id),
                    attachment.file_name,
                    attachment.sha256,
                    attachment.status,
                )

    async def list_review_attachments(self, review_id: str) -> list[AttachmentRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT a.* FROM attachments a
                JOIN review_attachments ra ON ra.attachment_id = a.id
                WHERE ra.review_id = $1::uuid
                ORDER BY ra.created_at
                """,
                review_id,
            )
        return [
            AttachmentRecord(
                id=str(row["id"]),
                file_name=row["file_name"],
                mime_type=row["mime_type"],
                size_bytes=row["size_bytes"],
                sha256=row["sha256"],
                storage_uri=row["storage_uri"],
                storage_path=row["storage_path"],
                uploader_id=row["uploader_id"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    # ── 人工决定 ──

    async def add_decision(
        self,
        review_id: str,
        *,
        decision: str,
        reviewer_id: str,
        reason: str | None,
        report_schema_version: str,
        expected_updated_at: datetime | None = None,
    ) -> DecisionRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT created_at, ai_verdict, human_status FROM review_jobs "
                    "WHERE id=$1::uuid FOR UPDATE",
                    review_id,
                )
                if row is None:
                    raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")
                if expected_updated_at is not None and row["created_at"] != expected_updated_at:
                    raise ApiError(ErrorCode.DECISION_CONFLICT, "报告已被修改，请重新拉取")
                decision_row = await conn.fetchrow(
                    """
                    INSERT INTO review_decisions
                        (review_id, decision, reviewer_id, reason, previous_verdict,
                         previous_human_status, report_schema_version)
                    VALUES ($1::uuid,$2,$3,$4,$5,$6,$7)
                    RETURNING *
                    """,
                    review_id,
                    decision,
                    reviewer_id,
                    reason,
                    row["ai_verdict"],
                    row["human_status"],
                    report_schema_version,
                )
                human_status = {
                    "approve": "approved",
                    "reject": "rejected",
                    "request_changes": "changes_requested",
                }[decision]
                await conn.execute(
                    "UPDATE review_jobs SET human_status=$1, current_decision_id=$2 "
                    "WHERE id=$3::uuid",
                    human_status,
                    str(decision_row["id"]),
                    review_id,
                )
        return DecisionRecord(
            id=str(decision_row["id"]),
            review_id=review_id,
            decision_no=decision_row["decision_no"],
            decision=decision_row["decision"],
            reviewer_id=decision_row["reviewer_id"],
            reason=decision_row["reason"],
            previous_verdict=decision_row["previous_verdict"],
            previous_human_status=decision_row["previous_human_status"],
            report_schema_version=decision_row["report_schema_version"],
            created_at=decision_row["created_at"],
        )

    async def list_decisions(self, review_id: str) -> list[DecisionRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM review_decisions WHERE review_id=$1::uuid ORDER BY decision_no",
                review_id,
            )
        return [
            DecisionRecord(
                id=str(row["id"]),
                review_id=str(row["review_id"]),
                decision_no=row["decision_no"],
                decision=row["decision"],
                reviewer_id=row["reviewer_id"],
                reason=row["reason"],
                previous_verdict=row["previous_verdict"],
                previous_human_status=row["previous_human_status"],
                report_schema_version=row["report_schema_version"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    # ── 复核任务 ──

    async def create_review_tasks(self, tasks: list[ReviewTaskRecord]) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            for task in tasks:
                await conn.execute(
                    """
                    INSERT INTO human_review_tasks
                        (id, review_id, issue_id, review_level, priority, assignee,
                         status, result, reason, source, due_at, version)
                    VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                    """,
                    UUID(task.id),
                    UUID(task.review_id),
                    UUID(task.issue_id) if task.issue_id else None,
                    task.review_level,
                    task.priority,
                    task.assignee,
                    task.status,
                    task.result,
                    task.reason,
                    task.source,
                    task.due_at,
                    task.version,
                )
                await conn.execute(
                    "INSERT INTO human_review_events (task_id, action, actor) "
                    "VALUES ($1::uuid,'create','system')",
                    UUID(task.id),
                )

    async def list_review_tasks(
        self, *, status: str | None = None, assignee: str | None = None, limit: int = 100
    ) -> list[ReviewTaskRecord]:
        clauses = []
        params: list[Any] = []
        if status:
            params.append(status)
            clauses.append(f"status=${len(params)}")
        if assignee:
            params.append(assignee)
            clauses.append(f"assignee=${len(params)}")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        sql = f"SELECT * FROM human_review_tasks {where} ORDER BY created_at DESC LIMIT ${len(params)}"
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [self._row_to_task(row) for row in rows]

    async def get_review_task(self, task_id: str) -> ReviewTaskRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM human_review_tasks WHERE id=$1::uuid", task_id
            )
        return self._row_to_task(row) if row else None

    async def update_review_task(
        self, task_id: str, *, expected_version: int, actor_id: str, **fields: Any
    ) -> ReviewTaskRecord:
        allowed = {"status", "assignee", "result", "reason", "started_at", "handled_at"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"不可更新字段: {sorted(unknown)}")
        values: list[Any] = []
        assignments: list[str] = []
        for key, value in fields.items():
            values.append(value)
            assignments.append(f"{key}=${len(values)}")
        values.extend([UUID(task_id), expected_version])
        sql = (
            f"UPDATE human_review_tasks SET version=version+1, {', '.join(assignments)} "
            f"WHERE id=${len(values) - 1}::uuid AND version=${len(values)} RETURNING *"
        )
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(sql, *values)
                if row is None:
                    exists = await conn.fetchval(
                        "SELECT version FROM human_review_tasks WHERE id=$1::uuid", task_id
                    )
                    if exists is None:
                        raise ApiError(ErrorCode.NOT_FOUND, "复核任务不存在")
                    raise ApiError(ErrorCode.DECISION_CONFLICT, "复核任务已被他人更新")
                await conn.execute(
                    "INSERT INTO human_review_events (task_id, action, actor, payload) "
                    "VALUES ($1::uuid,'update',$2,$3)",
                    UUID(task_id),
                    actor_id,
                    {key: str(value) for key, value in fields.items()},
                )
        return self._row_to_task(row)

    @staticmethod
    def _row_to_task(row: asyncpg.Record) -> ReviewTaskRecord:
        return ReviewTaskRecord(
            id=str(row["id"]),
            review_id=str(row["review_id"]),
            review_level=row["review_level"],
            priority=row["priority"],
            issue_id=str(row["issue_id"]) if row["issue_id"] else None,
            assignee=row["assignee"],
            status=row["status"],
            result=row["result"],
            reason=row["reason"],
            source=row["source"],
            due_at=row["due_at"],
            version=row["version"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            handled_at=row["handled_at"],
        )

    # ── 批次 ──

    async def create_batch(self, batch: BatchRecord) -> BatchRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO batches
                    (id, status, total, done, failed, caller_id, input_hash, idempotency_key)
                VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING
                RETURNING *
                """,
                UUID(batch.id),
                batch.status,
                batch.total,
                batch.done,
                batch.failed,
                batch.caller_id,
                batch.input_hash,
                batch.idempotency_key,
            )
            if row is None:
                row = await conn.fetchrow(
                    "SELECT * FROM batches WHERE idempotency_key=$1",
                    batch.idempotency_key,
                )
        return self._row_to_batch(row)

    async def get_batch(self, batch_id: str) -> BatchRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM batches WHERE id=$1::uuid", batch_id)
        return self._row_to_batch(row) if row else None

    async def update_batch(self, batch_id: str, **fields: Any) -> BatchRecord:
        values: list[Any] = []
        assignments: list[str] = []
        for key, value in fields.items():
            if key not in {"status", "done", "failed", "finished_at"}:
                raise ValueError(f"不可更新字段: {key}")
            values.append(value)
            assignments.append(f"{key}=${len(values)}")
        values.append(UUID(batch_id))
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"UPDATE batches SET {', '.join(assignments)} WHERE id=${len(values)}::uuid RETURNING *",
                *values,
            )
        if row is None:
            raise ApiError(ErrorCode.NOT_FOUND, "批次不存在")
        return self._row_to_batch(row)

    @staticmethod
    def _row_to_batch(row: asyncpg.Record) -> BatchRecord:
        return BatchRecord(
            id=str(row["id"]),
            status=row["status"],
            total=row["total"],
            done=row["done"],
            failed=row["failed"],
            caller_id=row["caller_id"],
            input_hash=row["input_hash"],
            idempotency_key=row["idempotency_key"],
            created_at=row["created_at"],
            finished_at=row["finished_at"],
        )

    # ── 附件 ──

    async def add_attachment(self, attachment: AttachmentRecord) -> AttachmentRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO attachments
                    (id, file_name, mime_type, size_bytes, sha256, storage_uri,
                     storage_path, uploader_id, status)
                VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (sha256) DO NOTHING
                RETURNING *
                """,
                UUID(attachment.id),
                attachment.file_name,
                attachment.mime_type,
                attachment.size_bytes,
                attachment.sha256,
                attachment.storage_uri,
                attachment.storage_path,
                attachment.uploader_id,
                attachment.status,
            )
            if row is None:
                row = await conn.fetchrow(
                    "SELECT * FROM attachments WHERE sha256=$1", attachment.sha256
                )
        return AttachmentRecord(
            id=str(row["id"]),
            file_name=row["file_name"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
            storage_uri=row["storage_uri"],
            storage_path=row["storage_path"],
            uploader_id=row["uploader_id"],
            status=row["status"],
            created_at=row["created_at"],
        )

    async def get_attachment(self, attachment_id: str) -> AttachmentRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM attachments WHERE id=$1::uuid", attachment_id
            )
        if row is None:
            return None
        return AttachmentRecord(
            id=str(row["id"]),
            file_name=row["file_name"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
            storage_uri=row["storage_uri"],
            storage_path=row["storage_path"],
            uploader_id=row["uploader_id"],
            status=row["status"],
            created_at=row["created_at"],
        )

    # ── 审计 ──

    async def append_audit(self, record: AuditRecord) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO audit_log (event_type, actor, review_id, payload) "
                "VALUES ($1,$2,$3::uuid,$4)",
                record.event_type,
                record.actor_id,
                record.review_id,
                record.payload,
            )

    async def list_audit(
        self, *, review_id: str | None = None, limit: int = 100
    ) -> list[AuditRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if review_id:
                rows = await conn.fetch(
                    "SELECT * FROM audit_log WHERE review_id=$1::uuid "
                    "ORDER BY created_at DESC LIMIT $2",
                    review_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT $1", limit
                )
        return [
            AuditRecord(
                id=str(row["id"]),
                event_type=row["event_type"],
                actor_id=row["actor"],
                review_id=str(row["review_id"]) if row["review_id"] else None,
                payload=row["payload"] or {},
                created_at=row["created_at"],
            )
            for row in rows
        ]
