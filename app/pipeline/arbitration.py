"""主审仲裁（条件触发）：只产出结构化意见，不修改原始投票、不直接写 ai_verdict。

M0 Mock 规则：
- 分歧/证据冲突/严重级分歧 → `need_human`；
- 成立性争议 → `dispute`；
- 其余按投票结果 `adopt` / `reject`。
真实模型接入后由仲裁 Prompt 产出，服务端按 docs/06 §3.2 做完整性校验。
"""

from __future__ import annotations

from typing import Any

from app.core.enums import ChiefDecision
from app.pipeline.verdict import VerdictResult


def run_arbitration(
    candidates: list[dict[str, Any]],
    traces: VerdictResult,
) -> dict[str, dict[str, Any]]:
    by_id = {trace.candidate_id: trace for trace in traces.traces}
    decisions: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        candidate_id = str(candidate["id"])
        trace = by_id.get(candidate_id)
        if trace is None:
            decisions[candidate_id] = {
                "chief_decision": ChiefDecision.NEED_HUMAN.value,
                "chief_reason": "仲裁输入缺少该候选的判定轨迹",
            }
            continue
        if "evidence_conflict" in trace.triggers:
            decisions[candidate_id] = {
                "chief_decision": ChiefDecision.NEED_HUMAN.value,
                "chief_reason": "证据冲突，需人工确认依据",
            }
        elif "severity_disputed" in trace.triggers:
            decisions[candidate_id] = {
                "chief_decision": ChiefDecision.NEED_HUMAN.value,
                "chief_reason": "严重级跨两级分歧，需人工裁决",
            }
        elif "validity_disputed" in trace.triggers:
            decisions[candidate_id] = {
                "chief_decision": ChiefDecision.DISPUTE.value,
                "chief_reason": "成立性投票无多数",
            }
        elif trace.status == "rejected":
            decisions[candidate_id] = {
                "chief_decision": ChiefDecision.REJECT.value,
                "chief_reason": "多数投票认定问题不成立",
            }
        else:
            decisions[candidate_id] = {
                "chief_decision": ChiefDecision.ADOPT.value,
                "chief_reason": None,
            }
    return decisions
