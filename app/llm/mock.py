"""确定性 Mock 模型：M0 用来跑通链路，不代表真实模型能力（docs/26）。

输出结构按 docs/05 的盲评/投票约定设计：
- 每条问题带 step_index、dimension、category、severity、rationale、claims；
- claims 只有 E3/E4（测试规范/推断），因此 M0 Mock 不会把问题判成 blocker，
  避免在没有知识库证据的情况下伪造 E1/E2 依据。
"""

from __future__ import annotations

from typing import Any

from app.llm.base import ReviewOpinion, VoteDecision

MockOpinion = ReviewOpinion

MOCK_ROLE_SEVERITY = {
    "chief_blind": "major",
    "jury_a": "major",
    "jury_b": "suggestion",
}
MOCK_ROLE_SEVERITY_BLOCKER = {
    "chief_blind": "blocker",
    "jury_a": "blocker",
    "jury_b": "blocker",
}


def _issue(
    *,
    step_index: int | None,
    dimension: str,
    category: str,
    severity: str,
    rationale: str,
    quote: str | None,
    suggestion: str,
) -> dict[str, Any]:
    return {
        "step_index": step_index,
        "dimension": dimension,
        "category": category,
        "severity": severity,
        "rationale": rationale,
        "evidence_quote": quote,
        "suggestion": suggestion,
        "claims": [
            {
                "claim_id": "claim_001",
                "claim_role": "core",
                "relation": "and",
                "claim_text": rationale,
                "evidence_level": "E3",
                "evidence_status": "supported",
                "evidence_refs": [],
            }
        ],
        "evidence_status": "ungrounded",
        "kb_grounded": False,
        "confidence": None,
    }


class MockChatClient:
    """按角色返回确定性盲评结果（同一用例重复调用结果一致）。"""

    def __init__(self, *, force_blocker: bool = False) -> None:
        self.force_blocker = force_blocker
        self.calls: list[dict[str, Any]] = []

    async def review(self, role: str, case: dict[str, Any]) -> ReviewOpinion:
        self.calls.append({"role": role, "operation": "blind_review"})
        steps = case.get("steps") or []
        missing_expected = [step for step in steps if not step.get("expected")]
        duplicate_actions: list[dict[str, Any]] = []
        seen: set[str] = set()
        for step in steps:
            action = (step.get("action") or "").strip()
            if action in seen:
                duplicate_actions.append(step)
            seen.add(action)

        blocker = self.force_blocker or len(missing_expected) >= 2
        severity = (MOCK_ROLE_SEVERITY_BLOCKER if blocker else MOCK_ROLE_SEVERITY)[role]

        issues: list[dict[str, Any]] = []
        for step in missing_expected:
            issues.append(
                _issue(
                    step_index=step.get("index"),
                    dimension="test_design",
                    category="预期不明确",
                    severity=severity,
                    rationale=f"第 {step.get('index')} 步只有操作、没有可判定的预期结果",
                    quote=step.get("action"),
                    suggestion="补充可观察、可判定的预期结果",
                )
            )
        for step in duplicate_actions:
            issues.append(
                _issue(
                    step_index=step.get("index"),
                    dimension="test_design",
                    category="重复冗余",
                    severity="suggestion",
                    rationale=f"第 {step.get('index')} 步与前面步骤操作重复，属于无意义重复",
                    quote=step.get("action"),
                    suggestion="删除重复步骤或说明两次执行的差异",
                )
            )

        if role == "jury_a" and not case.get("preconditions"):
            issues.append(
                _issue(
                    step_index=None,
                    dimension="business",
                    category="前置不足",
                    severity="major",
                    rationale="未提供任何前置条件，执行者无法确认初始状态",
                    quote=None,
                    suggestion="补充角色等级、背包状态等前置条件",
                )
            )
        if role == "jury_b" and roles_need_automation(case):
            issues.append(
                _issue(
                    step_index=None,
                    dimension="automation",
                    category="自动化不可行",
                    severity="suggestion",
                    rationale="用例未提供自动化上下文，状态断言能力未知",
                    quote=None,
                    suggestion="补充 framework/state_query_capabilities 或说明人工执行",
                )
            )

        return MockOpinion(
            role=role,
            summary=f"{role} 盲评：发现 {len(issues)} 条问题",
            issues=issues,
            model="mock",
            model_version="mock-v1",
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            cost_estimate=0.0,
        )

    async def vote(self, role: str, material: dict[str, Any]) -> VoteDecision:
        payload = mock_vote(role, material, blind_issue=material.get("blind_issue"))
        return VoteDecision(
            validity=str(payload.get("validity", "not_assessed")),
            severity=payload.get("severity"),
            reason=payload.get("reason"),
            model="mock",
            latency_ms=0,
            cost_estimate=0.0,
        )


def roles_need_automation(case: dict[str, Any]) -> bool:
    return not bool(case.get("automation_context_provided"))


def mock_vote(
    role: str,
    candidate: dict[str, Any],
    *,
    blind_issue: dict[str, Any] | None,
) -> dict[str, Any]:
    """投票：对融合后的中性描述逐条表态；不读取他人投票（防锚定）。"""

    severity = (blind_issue or {}).get("severity") or candidate.get("severity_proposal") or "major"
    return {
        "validity": "accept",
        "severity": severity,
        "reason": f"{role} 独立复核后认为问题成立",
    }
