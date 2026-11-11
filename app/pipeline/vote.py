"""投票轮：每条候选独立表态，未表态记 `not_assessed`。

- 投票材料只含候选标准化描述，不含 `proposed_by`、他人投票、原始论证与严重级倾向；
- Mock 与真实模型共用该流程；模型失败只影响该票，不伪造 reject；
- 三个角色并行投票，单条候选的失败不阻塞其他候选；
- 返回投票记录与调用元数据（报告附录/成本用）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.enums import VoteValidity
from app.llm.base import AdapterError, ReviewModel, VoteDecision
from app.llm.retry import call_with_retry
from app.storage.models import CandidateRecord, VoteRecord


def build_vote_material(candidate: CandidateRecord) -> dict[str, Any]:
    return {
        "candidate_id": candidate.id,
        "candidate_no": candidate.candidate_no,
        "step_index": candidate.step_index,
        "dimension": candidate.dimension,
        "description": candidate.standardized_text,
    }


async def run_vote(
    review_id: str,
    candidates: list[CandidateRecord],
    model: ReviewModel,
    roles: list[str],
) -> tuple[list[VoteRecord], list[dict[str, Any]]]:
    async def _one(candidate: CandidateRecord, role: str):
        material = build_vote_material(candidate)
        try:
            decision = await call_with_retry(
                lambda: model.vote(role, material), max_attempts=3, base_delay=2.0
            )
            return candidate, role, decision, "ok", None
        except AdapterError as exc:
            return (
                candidate,
                role,
                VoteDecision(
                    validity=VoteValidity.NOT_ASSESSED.value,
                    reason=f"vote_failed:{exc.code}",
                ),
                "failed",
                exc.code,
            )

    results = await asyncio.gather(
        *(_one(candidate, role) for candidate in candidates for role in roles)
    )

    votes: list[VoteRecord] = []
    calls: list[dict[str, Any]] = []
    for candidate, role, decision, status, error_code in results:
        validity = str(decision.validity)
        if validity not in {item.value for item in VoteValidity}:
            validity = VoteValidity.NOT_ASSESSED.value
        severity = decision.severity if validity == VoteValidity.ACCEPT.value else None
        votes.append(
            VoteRecord(
                id=f"vote-{candidate.id}-{role}",
                review_id=review_id,
                candidate_id=candidate.id,
                reviewer_id=role,
                validity=validity,
                severity=severity,
                reason=decision.reason,
            )
        )
        calls.append(
            {
                "role": role,
                "operation": "vote",
                "candidate_no": candidate.candidate_no,
                "model": decision.model or "-",
                "status": status,
                "error_code": error_code,
                "latency_ms": decision.latency_ms,
                "tokens": {
                    "request": decision.input_tokens,
                    "response": decision.output_tokens,
                },
                "cost_estimate": decision.cost_estimate,
            }
        )
    return votes, calls
