"""评审提交与查询服务（docs/03 §1–§2）。

提交语义以 docs/03 §1.1 为唯一口径：
- 新建 → 202；幂等命中 → 200 + 真实状态；
- 同键不同体 → 422；force 运行中 → 409；不返回 409 DUPLICATE。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.core.auth import Principal
from app.core.errors import ApiError, ErrorCode
from app.core.idempotency import compute_idempotency_key, compute_input_hash
from app.core.versioning import Versions
from app.pipeline.input_check import validate_request
from app.pipeline.render import render_markdown
from app.storage.models import AttachmentRecord, AuditRecord, ReviewJob, new_id
from app.storage.port import Storage


@dataclass
class SubmitResult:
    status_code: int
    body: dict[str, Any]


def _job_public(job: ReviewJob, *, replay: bool) -> dict[str, Any]:
    report_available = bool(job.report_json)
    body: dict[str, Any] = {
        "review_id": job.id,
        "status": job.status,
        "generation": job.generation,
        "case_version": job.case_version,
        "poll_url": f"/v1/reviews/{job.id}",
    }
    if replay:
        body["idempotent_replay"] = True
        body["report_available"] = report_available
        if report_available:
            body["report_json"] = job.report_json
    return body


class ReviewService:
    def __init__(self, storage: Storage, settings: Settings, versions: Versions) -> None:
        self.storage = storage
        self.settings = settings
        self.versions = versions

    async def submit(
        self,
        payload: Any,
        principal: Principal,
        *,
        idempotency_key: str | None = None,
    ) -> SubmitResult:
        """`idempotency_key` 仅供服务层测试注入（生产 API 不接受客户端指定）。"""

        normalized = validate_request(payload, self.settings, caller_id=principal.caller_id)
        attachments = await self._validate_attachments(normalized.case, principal)
        if normalized.options.get("strict_kb"):
            # M0 没有知识库覆盖任何模块，strict 模式必须明确拒绝（docs/03 §8）
            raise ApiError(
                ErrorCode.KB_MODULE_MISSING,
                "strict_kb=true 但该模块没有知识库覆盖",
                field="case.module",
            )

        input_hash = compute_input_hash(
            normalized.case,
            normalized.test_scope,
            normalized.automation_context,
            normalized.options,
        )
        computed_key = compute_idempotency_key(input_hash, self.versions)
        key = idempotency_key or computed_key

        roles = ("chief_blind", "jury_a", "jury_b")
        job = ReviewJob(
            id=new_id(),
            case_id=normalized.case["case_id"],
            case_version=normalized.case["case_version"],
            case_title=normalized.case["title"],
            module=normalized.case["module"],
            test_type=normalized.case["test_type"],
            test_type_source=normalized.test_type_source,
            status="queued",
            stage=None,
            input_hash=input_hash,
            idempotency_key=key,
            request_payload=payload,
            normalized_case=normalized.case,
            report_schema_version=self.settings.report_schema_version,
            test_scope=normalized.test_scope,
            automation_context=normalized.automation_context,
            participants=[f"{role}:{self.versions.models.get(role, 'mock')}" for role in roles],
            topology=self.settings.review_topology,
            topology_snapshot={
                "roles": list(roles),
                "models": {role: self.versions.models.get(role, "mock") for role in roles},
            },
            input_quality={},
            degraded=False,
            degraded_reasons=list(normalized.warnings),
            kb_content_version=self.versions.kb_content_version,
            kb_build_version=self.versions.kb_build_version,
            rubric_version=self.versions.rubric,
            prompt_versions=dict(self.versions.prompts),
            prompt_version_hash=self.versions.prompt_version_hash,
            retrieval_config_version=self.versions.retrieval_config,
            embedding_profile_id=None,
            model_config_version=self.versions.model_config,
            max_attempts=self.settings.queue_max_attempts,
            submitter_id=principal.actor_id,
        )

        if await self.storage.queue_depth() >= self.settings.max_queue_depth:
            raise ApiError(ErrorCode.QUEUE_FULL, "队列已满，请稍后重试", headers={"Retry-After": "30"})

        outcome = await self.storage.submit_review(job, force=normalized.options.get("force", False))
        if outcome.kind == "conflict":
            raise ApiError(
                ErrorCode.IDEMPOTENCY_KEY_CONFLICT,
                "相同幂等键对应不同请求体",
                field="case",
            )
        if outcome.kind == "in_progress":
            raise ApiError(
                ErrorCode.REVIEW_IN_PROGRESS,
                "旧代次仍在执行，force 需等待终态",
            )
        if outcome.kind == "replay":
            return SubmitResult(status_code=200, body=_job_public(outcome.job, replay=True))

        if attachments:
            await self.storage.bind_review_attachments(outcome.job.id, attachments)

        if normalized.options.get("force"):
            await self.storage.append_audit(
                AuditRecord(
                    id=new_id("a-"),
                    event_type="force_rerun",
                    actor_id=principal.actor_id,
                    review_id=outcome.job.id,
                    payload={"generation": outcome.job.generation, "parent": outcome.job.parent_review_id},
                )
            )
        return SubmitResult(status_code=202, body=_job_public(outcome.job, replay=False))

    async def get(self, review_id: str) -> dict[str, Any]:
        job = await self.storage.get_job(review_id)
        if job is None:
            raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")
        body: dict[str, Any] = {
            "review_id": job.id,
            "case_id": job.case_id,
            "module": job.module,
            "test_type": job.test_type,
            "test_type_source": job.test_type_source,
            "status": job.status,
            "stage": job.stage,
            "generation": job.generation,
            "case_version": job.case_version,
            "parent_review_id": job.parent_review_id,
            "report_schema_version": job.report_schema_version,
            "ai_verdict": job.ai_verdict,
            "human_status": job.human_status,
            "degraded": job.degraded,
            "degraded_reasons": job.degraded_reasons,
            "participants": job.participants,
            "topology": job.topology,
            "review_completeness": job.review_completeness,
            "input_quality": job.input_quality,
            "versions": (job.report_json or {}).get("versions") if job.report_json else None,
            "created_at": job.created_at.isoformat(),
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "report_available": bool(job.report_json),
        }
        if job.report_json:
            body["report"] = job.report_json
        else:
            body["poll_url"] = f"/v1/reviews/{job.id}"
        return body

    async def _validate_attachments(
        self, case: dict[str, Any], principal: Principal
    ) -> list[AttachmentRecord]:
        records: list[AttachmentRecord] = []
        for index, reference in enumerate(case.get("attachments") or []):
            field = f"case.attachments[{index}]"
            record = await self.storage.get_attachment(str(reference.get("attachment_id")))
            if record is None or record.status != "ready":
                raise ApiError(
                    ErrorCode.INPUT_INVALID,
                    f"{field} 引用的附件不存在或已删除",
                    field=field,
                )
            if record.sha256 != reference.get("sha256"):
                raise ApiError(
                    ErrorCode.INPUT_INVALID,
                    f"{field}.sha256 与已上传附件不一致",
                    field=f"{field}.sha256",
                )
            if record.uploader_id and record.uploader_id != principal.actor_id:
                raise ApiError(
                    ErrorCode.FORBIDDEN,
                    f"{field} 的附件不属于当前调用方",
                    field=field,
                )
            records.append(record)
        return records

    async def markdown(self, review_id: str) -> str:
        job = await self.storage.get_job(review_id)
        if job is None:
            raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")
        if not job.report_json:
            raise ApiError(ErrorCode.NOT_FOUND, "报告尚未生成")
        return render_markdown(job.report_json)

    async def delete(self, review_id: str, principal: Principal) -> None:
        """合规删除（M0 最小实现）：删除后同键再提交视为新任务。"""

        job = await self.storage.get_job(review_id)
        if job is None:
            raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")
        await self.storage.delete_job(review_id)
        await self.storage.append_audit(
            AuditRecord(
                id=new_id("a-"),
                event_type="review_deleted",
                actor_id=principal.actor_id,
                review_id=review_id,
                payload={"case_id": job.case_id},
            )
        )

    async def list_reviews(self, *, case_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        jobs = await self.storage.list_jobs(case_id=case_id, limit=limit)
        return [
            {
                "review_id": job.id,
                "case_id": job.case_id,
                "module": job.module,
                "status": job.status,
                "ai_verdict": job.ai_verdict,
                "human_status": job.human_status,
                "generation": job.generation,
                "created_at": job.created_at.isoformat(),
            }
            for job in jobs
        ]
