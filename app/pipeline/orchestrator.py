"""评审流水线（M0 Mock 全链路）：阶段推进、候选、投票、仲裁、结论、报告。

约束：
- `ai_verdict` 只调用 `pipeline.verdict.compute_verdict`，不在此拼装；
- 阶段状态与 `review_completeness` 分离（跳过 ≠ 完成）；
- 报告先通过 `schemas/report.schema.json` 校验，再写库并锁定；
- 任何阶段失败保留已完成阶段，按 docs/13 从失败处恢复（M0 先实现单次执行）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from app.config import Settings
from app.core.enums import (
    DegradedReason,
    Stage,
    StageStatus,
)
from app.core.observability import observe_stage
from app.llm.mock import MockChatClient
from app.pipeline import arbitration as arbitration_mod
from app.pipeline import fusion, render, vote
from app.pipeline.input_check import soft_check
from app.pipeline.stages import STAGE_NAMES, build_completeness
from app.pipeline.verdict import (
    IssueInput,
    VerdictInput,
    check_forbidden,
    compute_verdict,
)
from app.schemas.report import load_report_schema
from app.storage.models import (
    CandidateRecord,
    ReviewJob,
    ReviewTaskRecord,
    StageAttempt,
    StageRecord,
    VoteRecord,
    new_id,
    now,
)
from app.storage.port import Storage

logger = structlog.get_logger("testjury.pipeline")


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


@dataclass
class PipelineResult:
    report: dict[str, Any]
    markdown: str


class ReviewPipeline:
    def __init__(
        self,
        storage: Storage,
        settings: Settings,
        *,
        mock_client: MockChatClient | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.mock_client = mock_client or MockChatClient()

    # ── 阶段辅助 ──

    async def _stage(
        self,
        job: ReviewJob,
        stage: Stage,
        status: StageStatus,
        *,
        output_ref: str | None = None,
        error: str | None = None,
        fencing_token: int | None = None,
    ) -> None:
        started = now()
        await self.storage.upsert_stage(
            StageRecord(
                review_id=job.id,
                stage=stage.value,
                status=status.value,
                fencing_token=fencing_token,
                output_ref=output_ref,
                started_at=started if status is StageStatus.RUNNING else None,
                finished_at=started if status is not StageStatus.RUNNING else None,
                error=error,
            )
        )
        if status is not StageStatus.RUNNING:
            await self.storage.add_stage_attempt(
                StageAttempt(
                    review_id=job.id,
                    stage=stage.value,
                    attempt_no=job.attempt_count or 1,
                    status=status.value,
                    fencing_token=fencing_token,
                    output_ref=output_ref,
                    started_at=started,
                    finished_at=started,
                    error_message=error,
                    worker_id=job.locked_by,
                )
            )
            observe_stage(stage.value, status.value, 0.0)
        logger.info(
            "review_stage",
            review_id=job.id,
            stage=stage.value,
            status=status.value,
            attempt=job.attempt_count or 1,
        )

    # ── 主流程 ──

    async def run(self, job: ReviewJob, versions: Any) -> PipelineResult:
        started = time.perf_counter()
        case = (job.normalized_case or {}) or {}
        degraded: list[str] = []
        states: dict[str, str] = {name: StageStatus.PENDING.value for name in STAGE_NAMES}
        model_calls: list[dict[str, Any]] = []

        # 1. 输入软校验
        await self._stage(job, Stage.INPUT_CHECK, StageStatus.RUNNING, fencing_token=job.fencing_token)
        input_quality = soft_check(case)
        states[Stage.INPUT_CHECK.value] = StageStatus.SUCCEEDED.value
        await self._stage(job, Stage.INPUT_CHECK, StageStatus.SUCCEEDED)

        # 2. 预处理（仅 raw_text）
        raw_text = bool(case.get("raw_text"))
        if raw_text and not case.get("steps"):
            steps = _parse_raw_text(str(case.get("raw_text")))
            if steps:
                case = dict(case)
                case["steps"] = steps
                states[Stage.PREPROCESS.value] = StageStatus.SUCCEEDED.value
                await self._stage(job, Stage.PREPROCESS, StageStatus.SUCCEEDED, output_ref="normalized_case")
            else:
                degraded.append(DegradedReason.RAW_TEXT_UNPARSED.value)
                states[Stage.PREPROCESS.value] = StageStatus.FAILED.value
                await self._stage(job, Stage.PREPROCESS, StageStatus.FAILED, error="raw_text 无法解析")
                return await self._finish_failed(job, degraded, states, started)
        else:
            states[Stage.PREPROCESS.value] = StageStatus.SKIPPED.value
            await self._stage(job, Stage.PREPROCESS, StageStatus.SKIPPED)

        # 3. 知识库检索（M0 未接入）
        degraded.append(DegradedReason.KB_MODULE_MISSING.value)
        states[Stage.KB_RETRIEVE.value] = StageStatus.SKIPPED.value
        await self._stage(job, Stage.KB_RETRIEVE, StageStatus.SKIPPED)

        # 4. 三路盲评
        await self._stage(job, Stage.BLIND_REVIEW, StageStatus.RUNNING, fencing_token=job.fencing_token)
        case_for_review = dict(case)
        case_for_review["automation_context_provided"] = bool(job.automation_context)
        roles = ["chief_blind", "jury_a", "jury_b"]
        opinions = []
        for role in roles:
            call_started = time.perf_counter()
            opinion = self.mock_client.review(role, case_for_review)
            opinions.append(opinion)
            model_calls.append(
                {
                    "role": role,
                    "model": versions.models.get(role, "mock"),
                    "status": "ok",
                    "latency_ms": int((time.perf_counter() - call_started) * 1000),
                    "tokens": {"request": 0, "response": 0},
                }
            )
        states[Stage.BLIND_REVIEW.value] = StageStatus.SUCCEEDED.value
        await self._stage(job, Stage.BLIND_REVIEW, StageStatus.SUCCEEDED, output_ref="blind_opinions")
        blind_ratio = "3/3"

        # 5. 融合
        await self._stage(job, Stage.FUSION, StageStatus.RUNNING, fencing_token=job.fencing_token)
        candidates = fusion.fuse(
            job.id, case, opinions, step_tolerance=self.settings.step_tolerance
        )
        await self.storage.replace_candidates(job.id, candidates)
        states[Stage.FUSION.value] = StageStatus.SUCCEEDED.value
        await self._stage(job, Stage.FUSION, StageStatus.SUCCEEDED, output_ref="review_candidates")

        # 6. 投票
        await self._stage(job, Stage.VOTE, StageStatus.RUNNING, fencing_token=job.fencing_token)
        vote_records = vote.run_vote(job.id, candidates, opinions, roles)
        await self.storage.add_votes(job.id, vote_records)
        vote_ratio = _global_vote_ratio(vote_records, len(roles))
        states[Stage.VOTE.value] = StageStatus.SUCCEEDED.value
        await self._stage(job, Stage.VOTE, StageStatus.SUCCEEDED, output_ref="issue_votes")

        # 7. 仲裁（条件触发）
        votes_by_candidate = _group_votes(vote_records)
        verdict_input = _build_verdict_input(candidates, votes_by_candidate, len(roles))
        preliminary = compute_verdict(verdict_input)
        arbitration_required = preliminary.arbitration_required
        arbitration_decisions: dict[str, dict[str, Any]] = {}
        if arbitration_required:
            await self._stage(
                job, Stage.ARBITRATION, StageStatus.RUNNING, fencing_token=job.fencing_token
            )
            arbitration_decisions = arbitration_mod.run_arbitration(
                [candidate.__dict__ for candidate in candidates], preliminary
            )
            states[Stage.ARBITRATION.value] = StageStatus.SUCCEEDED.value
            await self._stage(job, Stage.ARBITRATION, StageStatus.SUCCEEDED, output_ref="arbitration")
            arbitration_value = "ok"
        else:
            states[Stage.ARBITRATION.value] = StageStatus.SKIPPED.value
            degraded.append(DegradedReason.ARBITRATION_SKIPPED.value)
            await self._stage(job, Stage.ARBITRATION, StageStatus.SKIPPED)
            arbitration_value = "skipped"

        # 8. 结论（唯一入口）
        await self._stage(job, Stage.VERDICT, StageStatus.RUNNING, fencing_token=job.fencing_token)
        result = compute_verdict(verdict_input)
        violations = check_forbidden(result, len(roles))
        if violations:  # pragma: no cover - 实现缺陷应立即暴露
            raise RuntimeError("verdict 产生禁止组合: " + "; ".join(violations))
        states[Stage.VERDICT.value] = StageStatus.SUCCEEDED.value
        await self._stage(job, Stage.VERDICT, StageStatus.SUCCEEDED, output_ref="ai_verdict")

        # 9. 报告
        completeness = build_completeness(
            states,
            raw_text=raw_text and not case.get("steps"),
            kb_covered=False,
            arbitration_required=arbitration_required,
            blind=blind_ratio,
            vote=vote_ratio,
            arbitration=arbitration_value,
        )
        report = _build_report(
            job=job,
            case=case,
            candidates=candidates,
            votes_by_candidate=votes_by_candidate,
            result=result,
            arbitration_decisions=arbitration_decisions,
            completeness=completeness,
            degraded=degraded,
            versions=versions,
            opinions=opinions,
            model_calls=model_calls,
            input_quality=input_quality,
        )
        schema = load_report_schema(self.settings.report_schema_version)
        schema.validate(report)  # 失败直接抛出，不写半成品报告

        markdown = render.render_markdown(report)
        await self._stage(job, Stage.RENDER, StageStatus.RUNNING, fencing_token=job.fencing_token)
        states[Stage.RENDER.value] = StageStatus.SUCCEEDED.value
        report["review_completeness"] = build_completeness(
            states,
            raw_text=raw_text and not case.get("steps"),
            kb_covered=False,
            arbitration_required=arbitration_required,
            blind=blind_ratio,
            vote=vote_ratio,
            arbitration=arbitration_value,
        )
        await self._stage(job, Stage.RENDER, StageStatus.SUCCEEDED, output_ref="report_json")

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        report["timings"] = {
            "queue_ms": max(
                0, int((job.started_at - job.created_at).total_seconds() * 1000)
            )
            if job.started_at
            else 0,
            "execution_ms": elapsed_ms,
            "model_call_ms": sum(call["latency_ms"] for call in model_calls),
        }
        return PipelineResult(report=report, markdown=markdown)

    async def _finish_failed(
        self,
        job: ReviewJob,
        degraded: list[str],
        states: dict[str, str],
        started: float,
    ) -> PipelineResult:
        completeness = build_completeness(
            states,
            raw_text=False,
            kb_covered=False,
            arbitration_required=False,
            blind="0/3",
            vote="0/3",
        )
        report = {
            "review_id": job.id,
            "case_id": job.case_id,
            "status": "failed",
            "stage": "preprocess",
            "ai_verdict": None,
            "human_status": job.human_status,
            "report_schema_version": self.settings.report_schema_version,
            "issues": [],
            "versions": {},
            "review_completeness": completeness,
            "degraded": True,
            "degraded_reasons": degraded,
        }
        return PipelineResult(report=report, markdown="# 评审失败\n")


def _parse_raw_text(text: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for line in text.splitlines():
        cleaned = line.strip().lstrip("-*0123456789.、 ")
        if not cleaned:
            continue
        if "->" in cleaned:
            action, _, expected = cleaned.partition("->")
        elif "→" in cleaned:
            action, _, expected = cleaned.partition("→")
        else:
            action, expected = cleaned, ""
        steps.append(
            {
                "index": len(steps) + 1,
                "action": action.strip(),
                "expected": expected.strip() or None,
            }
        )
        if len(steps) >= 200:
            break
    return steps


def _group_votes(votes: list[VoteRecord]) -> dict[str, list[VoteRecord]]:
    grouped: dict[str, list[VoteRecord]] = {}
    for record in votes:
        grouped.setdefault(record.candidate_id, []).append(record)
    return grouped


def _build_verdict_input(
    candidates: list[CandidateRecord],
    votes: dict[str, list[VoteRecord]],
    participants: int,
) -> VerdictInput:
    issues = []
    for candidate in candidates:
        records = votes.get(candidate.id, [])
        issues.append(
            IssueInput(
                candidate_id=candidate.id,
                votes=[
                    {"validity": record.validity, "severity": record.severity}
                    for record in records
                ],
                claims=[
                    {
                        "role": claim.get("claim_role"),
                        "status": claim.get("evidence_status"),
                        "level": claim.get("evidence_level"),
                    }
                    for claim in candidate.claims
                ]
                if candidate.claims
                else None,
                evidence_status=candidate.evidence_status,
            )
        )
    return VerdictInput(participants=participants, issues=issues)


def _global_vote_ratio(votes: list[VoteRecord], participants: int) -> str:
    if participants == 0:
        return "0/3"
    if not votes:
        return "0/3"
    valid = sum(1 for record in votes if record.validity != "not_assessed")
    ratio = round(valid / len(votes) * participants)
    return f"{max(0, min(participants, ratio))}/{participants}"


def _severity_summary(votes: list[VoteRecord]) -> dict[str, int]:
    distribution = {"blocker": 0, "major": 0, "suggestion": 0}
    for record in votes:
        if record.validity == "accept" and record.severity in distribution:
            distribution[record.severity] += 1
    return distribution


def _vote_summary(votes: list[VoteRecord], participants: int) -> dict[str, Any]:
    support = sum(1 for record in votes if record.validity == "accept")
    reject = sum(1 for record in votes if record.validity == "reject")
    not_assessed = sum(1 for record in votes if record.validity == "not_assessed")
    uncertain = sum(1 for record in votes if record.validity == "uncertain")
    accepted = [record for record in votes if record.validity == "accept"]
    severities = [
        {"suggestion": 0, "major": 1, "blocker": 2}[record.severity]
        for record in accepted
        if record.severity
    ]
    severity_disputed = bool(severities) and (max(severities) - min(severities) >= 2)
    effective = support + reject + uncertain
    return {
        "support": support,
        "reject": reject,
        "not_assessed": not_assessed,
        "uncertain": uncertain,
        "support_ratio": round(support / participants, 2) if participants else 0.0,
        "severity_distribution": _severity_summary(votes),
        "severity_disputed": severity_disputed,
        "vote_completeness": f"{min(effective, participants)}/{participants}",
    }


def _build_report(
    *,
    job: ReviewJob,
    case: dict[str, Any],
    candidates: list[CandidateRecord],
    votes_by_candidate: dict[str, list[VoteRecord]],
    result: Any,
    arbitration_decisions: dict[str, dict[str, Any]],
    completeness: dict[str, Any],
    degraded: list[str],
    versions: Any,
    opinions: list[Any],
    model_calls: list[dict[str, Any]],
    input_quality: dict[str, Any],
) -> dict[str, Any]:
    candidate_by_id = {candidate.id: candidate for candidate in candidates}
    included = [
        trace for trace in result.traces if trace.issue_status != "rejected"
    ]
    issues: list[dict[str, Any]] = []
    human_items: list[dict[str, Any]] = []
    for issue_no, trace in enumerate(included, start=1):
        candidate = candidate_by_id[trace.candidate_id]
        records = votes_by_candidate.get(candidate.id, [])
        arbitration = arbitration_decisions.get(candidate.id, {})
        severity = trace.severity or candidate.severity_proposal or "major"
        issue = {
            "issue_no": issue_no,
            "candidate_id": candidate.id,
            "step_index": candidate.step_index,
            "dimension": candidate.dimension,
            "severity": severity,
            "category": candidate.category or "未分类",
            "evidence_quote": None,
            "rationale": candidate.standardized_text,
            "suggestion": None,
            "kb_grounded": False,
            "kb_refs": [],
            "evidence_type": "testing_standard",
            "evidence_strength": "medium",
            "evidence_status": trace.evidence_status,
            "evidence_refs": [],
            "proposed_by": list(candidate.proposed_by),
            "votes": {
                record.reviewer_id: {
                    "validity": record.validity,
                    "severity": record.severity,
                }
                for record in records
            },
            "vote_summary": _vote_summary(records, len(records)),
            "confidence": None,
            "confidence_source": "uncalibrated",
            "model_confidence": None,
            "validation_status": "passed",
            "evidence_support_status": None,
            "decision_status": None,
            "status": trace.issue_status,
            "chief_decision": arbitration.get("chief_decision")
            or ("adopt" if trace.issue_status == "adopted" else "need_human"),
            "chief_reason": arbitration.get("chief_reason"),
            "human_verdict": None,
        }
        issues.append(issue)

        triggers = set(trace.triggers)
        if triggers & {
            "partially_grounded_blocker",
            "blocker_in_partial_review",
            "severity_disputed",
            "evidence_conflict",
            "validity_disputed",
        } or trace.issue_status in ("need_human", "disputed"):
            if "partially_grounded_blocker" in triggers:
                reason, priority = "partially_grounded_blocker", "blocker"
            elif "evidence_conflict" in triggers:
                reason, priority = "evidence_conflict", "evidence_conflict"
            elif "severity_disputed" in triggers:
                reason, priority = "severity_disputed", "severity_disputed"
            elif trace.issue_status == "disputed":
                reason, priority = "validity_disputed", "normal"
            else:
                reason, priority = "need_human", "normal"
            human_items.append({"issue_no": issue_no, "reason": reason, "priority": priority})

    counts = {"total_issues": len(issues), "blocker": 0, "major": 0, "suggestion": 0}
    for issue in issues:
        counts[issue["severity"]] += 1
    degraded_list = sorted(set(degraded))
    if not job.test_scope:
        degraded_list.append(DegradedReason.SCOPE_MISSING.value)
    if not job.automation_context:
        degraded_list.append(DegradedReason.AUTOMATION_CONTEXT_MISSING.value)

    report = {
        "review_id": job.id,
        "case_id": job.case_id,
        "case_version": job.case_version,
        "module": job.module,
        "test_type": job.test_type,
        "test_type_source": job.test_type_source,
        "generation": job.generation,
        "parent_review_id": job.parent_review_id,
        "status": "done",
        "stage": "render",
        "ai_verdict": result.ai_verdict,
        "human_status": job.human_status,
        "report_schema_version": job.report_schema_version,
        "degraded": bool(degraded_list),
        "degraded_reasons": sorted(set(degraded_list)),
        "participants": [
            f"{role}:{versions.models.get(role, 'mock')}"
            for role in ("chief_blind", "jury_a", "jury_b")
        ],
        "topology": job.topology,
        "review_participants": [
            {
                "participant_id": f"p-{index:02d}",
                "role_id": role,
                "status": "active",
                "model": versions.models.get(role, "mock"),
                "actual_model": versions.models.get(role, "mock"),
            }
            for index, role in enumerate(("chief_blind", "jury_a", "jury_b"), start=1)
        ],
        "review_completeness": completeness,
        "input_quality": input_quality,
        "versions": versions.report_versions(),
        "summary": counts,
        "issues": issues,
        "human_review_items": human_items,
        "kb_gaps": [],
        "scope": {
            "feature_point": (job.test_scope or {}).get("feature_point"),
            "scope_version": (job.test_scope or {}).get("scope_version"),
            "provided": bool(job.test_scope),
            "coverage_claims_allowed": False,
            "note": "v1 仅做单条用例评审，不输出功能点整体覆盖率",
        },
        "decision_summary": {"human_status": job.human_status, "latest_decision": None, "history_count": 0},
        "appendix": {
            "raw_opinions": {
                opinion.role: {"summary": opinion.summary, "issues": opinion.issues}
                for opinion in opinions
            },
            "disagreements": [],
            "model_runs": model_calls,
            "normalized_case": case,
        },
        "created_at": _utc_iso(job.created_at),
        "finished_at": _utc_iso(now()),
    }
    return report


async def create_review_tasks_after_report(
    storage: Storage, review_id: str, report: dict[str, Any]
) -> None:
    tasks: list[ReviewTaskRecord] = []
    for item in report.get("human_review_items") or []:
        tasks.append(
            ReviewTaskRecord(
                id=new_id("t-"),
                review_id=review_id,
                issue_id=None,
                review_level="issue",
                priority=item.get("priority", "normal"),
                status="pending",
                reason=item.get("reason"),
                source="auto",
            )
        )
    if tasks:
        await storage.create_review_tasks(tasks)


def job_is_complete(job: ReviewJob) -> bool:
    return job.status in ("done", "completed_with_warnings", "failed", "cancelled")
