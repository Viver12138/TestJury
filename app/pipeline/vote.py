"""投票轮（M0 Mock）：每条候选独立表态，未表态记 `not_assessed`。

防锚定（docs/12 §7）：投票材料只含候选标准化描述，不含 `proposed_by`、
他人投票、severity_proposal 与原始论证。
"""

from __future__ import annotations

from typing import Any

from app.core.enums import VoteValidity
from app.llm.mock import MockOpinion, mock_vote
from app.storage.models import CandidateRecord, VoteRecord


def build_vote_material(candidate: CandidateRecord) -> dict[str, Any]:
    return {
        "candidate_id": candidate.id,
        "candidate_no": candidate.candidate_no,
        "step_index": candidate.step_index,
        "dimension": candidate.dimension,
        "description": candidate.standardized_text,
    }


def run_vote(
    review_id: str,
    candidates: list[CandidateRecord],
    opinions: list[MockOpinion],
    roles: list[str],
) -> list[VoteRecord]:
    by_role = {opinion.role: opinion for opinion in opinions}
    votes: list[VoteRecord] = []
    for candidate in candidates:
        for role in roles:
            opinion = by_role.get(role)
            matching = None
            if opinion is not None:
                for issue in opinion.issues:
                    if (
                        issue.get("step_index") == candidate.step_index
                        and str(issue.get("category")) == candidate.category
                    ):
                        matching = issue
                        break
            payload = mock_vote(role, candidate.__dict__, blind_issue=matching)
            validity = str(payload.get("validity", VoteValidity.NOT_ASSESSED.value))
            severity = payload.get("severity") if validity == VoteValidity.ACCEPT.value else None
            votes.append(
                VoteRecord(
                    id=f"vote-{candidate.id}-{role}",
                    review_id=review_id,
                    candidate_id=candidate.id,
                    reviewer_id=role,
                    validity=validity,
                    severity=severity,
                    reason=payload.get("reason"),
                )
            )
    return votes
