"""ACC-M0-012：Verdict 属性不变量与禁止组合（docs/12 §8，I1–I8）。

随机生成 ≥1000 组输入，生产实现与参考判定器必须逐组一致，且不得出现禁止组合。
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any

import pytest

from app.pipeline.verdict import check_forbidden, compute_verdict

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from verdict_reference import evaluate  # noqa: E402

SEEDS = list(range(12))


def _random_claim(rng: random.Random) -> dict[str, Any]:
    roles = ["core"] + ["supporting"] * rng.randint(0, 2)
    claims = []
    for role in roles:
        claims.append(
            {
                "role": role,
                "status": rng.choice(["supported", "supported", "unsupported", "insufficient", "conflicted"]),
                "level": rng.choice(["E1", "E2", "E2", "E3", "E4"]),
            }
        )
    return claims


def _random_issue(rng: random.Random, participants: int, candidate_id: str) -> dict[str, Any]:
    votes = []
    for _ in range(participants):
        validity = rng.choices(
            ["accept", "reject", "uncertain", "not_assessed"],
            weights=[5, 2, 2, 3],
        )[0]
        severity = rng.choice(["blocker", "major", "suggestion"]) if validity == "accept" else None
        votes.append([validity, severity])
    issue: dict[str, Any] = {"candidate_id": candidate_id, "votes": votes}
    if rng.random() < 0.6:
        issue["claims"] = _random_claim(rng)
    else:
        issue["evidence_status"] = rng.choice(
            ["grounded", "partially_grounded", "ungrounded", "conflicted", "insufficient"]
        )
    return issue


def _random_payload(rng: random.Random) -> dict[str, Any]:
    participants = rng.choice([0, 1, 2, 3, 3, 3])
    count = rng.choice([0, 1, 1, 2, 3])
    return {
        "participants": participants,
        "issues": [_random_issue(rng, participants, f"C{index + 1}") for index in range(count)],
    }


@pytest.mark.parametrize("seed", SEEDS)
def test_production_matches_reference_and_invariants(seed: int) -> None:
    rng = random.Random(seed)
    checked = 0
    for _ in range(150):
        payload = _random_payload(rng)
        expected = evaluate(payload)
        result = compute_verdict(payload)
        actual = result.to_dict()
        for key in ("ai_verdict", "issue_statuses", "human_review_required", "arbitration_required"):
            assert actual[key] == expected[key], f"seed={seed} payload={payload} key={key}"

        # I1 / I3 / I4：结论集合受限，approved 永不出现
        assert actual["ai_verdict"] in (None, "blocked", "conditional", "need_human")
        assert actual["ai_verdict"] != "approved"

        # docs/12 §8 禁止组合
        assert check_forbidden(result, payload["participants"]) == []

        if payload["participants"] < 2:
            assert actual["ai_verdict"] is None
        if actual["ai_verdict"] == "blocked":
            assert any(trace.status == "blocker" for trace in result.traces)
        if actual["ai_verdict"] == "conditional":
            assert not any(
                trace.status in ("disputed", "need_human") for trace in result.traces
            )
        for trace in result.traces:
            if trace.status == "blocker":
                assert trace.evidence_status in ("grounded", "partially_grounded")
                assert trace.severity == "blocker"

        # 幂等：同一输入重复计算结果一致
        assert compute_verdict(payload).to_dict() == actual
        checked += 1

    assert checked == 150


def test_order_and_model_fields_do_not_change_result() -> None:
    payload = {
        "participants": 3,
        "issues": [
            {
                "candidate_id": "C1",
                "votes": [["accept", "major"], ["accept", "suggestion"], ["reject", None]],
                "evidence_status": "grounded",
                "model_claimed_verdict": "approved",
                "human_status": "approved",
            }
        ],
    }
    base = compute_verdict(payload).to_dict()

    mutated = {
        "participants": 3,
        "human_status": "approved",
        "ai_verdict": "approved",
        "issues": [
            {
                **payload["issues"][0],
                "ai_verdict": "approved",
                "human_status": "approved",
            }
        ],
    }
    assert compute_verdict(mutated).to_dict() == base
    assert base["ai_verdict"] == "conditional"
