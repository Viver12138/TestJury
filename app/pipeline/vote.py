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
from app.llm.attempts import attempt_log
from app.llm.base import AdapterError, ReviewModel, VoteDecision
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
    *,
    timeout_seconds: int | None = None,
) -> tuple[list[VoteRecord], list[dict[str, Any]]]:
    """并行投票；每个候选 × 角色是一次独立调用，超时按该票 failed 处理。"""

    async def _one(candidate: CandidateRecord, role: str):
        material = build_vote_material(candidate)
        audit: list[dict[str, Any]] = []
        token = attempt_log.set(audit)
        try:
            # Retry 的唯一所有者是 ChatReviewModel._complete；此处不再包一层，
            # 避免一次投票最多触发 3×3=9 次供应商调用（docs/18 §3）。
            vote_call = model.vote(role, material)
            if timeout_seconds:
                decision = await asyncio.wait_for(vote_call, timeout=timeout_seconds)
            else:
                decision = await vote_call
            return candidate, role, decision, "ok", None
        except AdapterError as exc:
            return (
                candidate,
                role,
                VoteDecision(
                    validity=VoteValidity.NOT_ASSESSED.value,
                    reason=f"vote_failed:{exc.code}",
                    attempts=list(getattr(exc, "attempts", []) or audit),
                ),
                "failed",
                exc.code,
            )
        except TimeoutError:
            return (
                candidate,
                role,
                VoteDecision(
                    validity=VoteValidity.NOT_ASSESSED.value,
                    reason="vote_failed:MODEL_TIMEOUT",
                    attempts=list(audit),
                ),
                "failed",
                "MODEL_TIMEOUT",
            )
        finally:
            attempt_log.reset(token)

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
                "attempts": list(getattr(decision, "attempts", []) or []),
                "provider": getattr(decision, "provider", None),
                "request_hash": getattr(decision, "request_hash", None),
                "response_hash": getattr(decision, "response_hash", None),
                "raw_request": getattr(decision, "raw_request", None),
                "raw_response": getattr(decision, "raw_response", None),
                "warnings": list(decision.warnings),
                "masking_policy_id": getattr(decision, "masking_policy_id", None),
                "masking_policy_version": getattr(decision, "masking_policy_version", None),
                "masking_report": getattr(decision, "masking_report", None),
            }
        )
    return votes, calls
