"""Verdict 参考判定器（规范实现，非生产代码）。

用途
----
把 `docs/12-评审决策真值表.md` 的规则表达为一段可执行的纯函数，供：

1. `design/verdict_cases.yaml` 的固定/边界用例做一致性校验；
2. `scripts/check_verdict_cases.py` 的属性测试随机生成输入，验证 8 条不变量；
3. M0 阶段 `app/pipeline/verdict.py` 实现后，用同一批用例做**一致性对照**：
   生产实现与参考判定器对同一输入必须给出相同 `ai_verdict` / issue 状态。

边界声明
--------
- 本文件不是生产实现，不读数据库、不写日志、不做 I/O；生产唯一入口仍是
  `app/pipeline/verdict.py`（见 docs/06 §3.1、docs/12 §0）。
- 仲裁的"主审补充/驳回"语义（docs/12 §7）依赖仲裁输入，不在本判定器的输入
  范围内；本判定器只计算 `arbitration_required` 触发位，不模拟主审决策。
- 输入中的 `model_claimed_verdict` / `human_status` 等字段被显式忽略，用于验证
  "AI 结论由服务端计算、人工决定不影响 ai_verdict"。

规则来源
--------
docs/12 §2（成立性）、§3（严重级）、§4（问题级结论与顺序）、§4.1（claim 聚合）、
§5（报告级 Verdict）、§6（不完整评审）、§7（仲裁触发）、§8（禁止组合）。
"""

from __future__ import annotations

from typing import Any

VALIDITY_STATES = ("accept", "reject", "uncertain", "not_assessed")
SEVERITY_ORDER = {"suggestion": 0, "major": 1, "blocker": 2}
SEVERITY_STATES = tuple(SEVERITY_ORDER)
EVIDENCE_STATUS = (
    "grounded",
    "partially_grounded",
    "ungrounded",
    "conflicted",
    "insufficient",
)
CLAIM_STATUS = ("supported", "unsupported", "conflicted", "insufficient")
CLAIM_ROLES = ("core", "supporting")
CLAIM_LEVELS = ("E1", "E2", "E3", "E4")

ISSUE_STATUSES = (
    "blocker",
    "major",
    "suggestion",
    "rejected",
    "disputed",
    "need_human",
)


class VerdictInputError(ValueError):
    """输入违反 docs/12 的字段约束（不是业务结论，而是数据非法）。"""


def _norm_votes(raw_votes: Any, participants: int, label: str) -> list[tuple[str, str | None]]:
    if not isinstance(raw_votes, list):
        raise VerdictInputError(f"{label}.votes 必须是数组")
    if len(raw_votes) != participants:
        raise VerdictInputError(
            f"{label}.votes 长度 {len(raw_votes)} 与 participants {participants} 不一致"
        )
    votes: list[tuple[str, str | None]] = []
    for index, raw in enumerate(raw_votes):
        if isinstance(raw, dict):
            validity = raw.get("validity")
            severity = raw.get("severity")
        elif isinstance(raw, (list, tuple)) and len(raw) == 2:
            validity, severity = raw
        else:
            raise VerdictInputError(f"{label}.votes[{index}] 必须是 [validity, severity]")
        if validity not in VALIDITY_STATES:
            raise VerdictInputError(f"{label}.votes[{index}].validity 非法: {validity!r}")
        if severity is not None:
            if severity not in SEVERITY_ORDER:
                raise VerdictInputError(f"{label}.votes[{index}].severity 非法: {severity!r}")
            if validity != "accept":
                raise VerdictInputError(
                    f"{label}.votes[{index}] validity={validity} 时不得携带 severity"
                )
        votes.append((validity, severity))
    return votes


def _norm_claims(raw_claims: Any, label: str) -> list[dict[str, Any]] | None:
    if raw_claims is None:
        return None
    if not isinstance(raw_claims, list) or not raw_claims:
        raise VerdictInputError(f"{label}.claims 必须是非空数组")
    claims: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_claims):
        if not isinstance(raw, dict):
            raise VerdictInputError(f"{label}.claims[{index}] 必须是对象")
        role = raw.get("role")
        status = raw.get("status")
        level = raw.get("level")
        if role not in CLAIM_ROLES:
            raise VerdictInputError(f"{label}.claims[{index}].role 非法: {role!r}")
        if status not in CLAIM_STATUS:
            raise VerdictInputError(f"{label}.claims[{index}].status 非法: {status!r}")
        if level not in CLAIM_LEVELS:
            raise VerdictInputError(f"{label}.claims[{index}].level 非法: {level!r}")
        claims.append({"role": role, "status": status, "level": level})
    cores = [c for c in claims if c["role"] == "core"]
    if len(cores) != 1:
        raise VerdictInputError(f"{label}.claims 必须且只能有 1 个 core，实际 {len(cores)}")
    return claims


def aggregate_claim_evidence(claims: list[dict[str, Any]]) -> str:
    """按 docs/12 §4.1 聚合问题级 evidence_status（固定算法，不由模型自由判断）。"""
    statuses = [c["status"] for c in claims]
    if "conflicted" in statuses:
        return "conflicted"
    levels = [c["level"] for c in claims]
    if not any(level in ("E1", "E2") for level in levels):
        return "ungrounded"
    core = next(c for c in claims if c["role"] == "core")
    if core["status"] in ("unsupported", "insufficient"):
        return "insufficient"
    if any(c["status"] != "supported" for c in claims):
        return "partially_grounded"
    if core["level"] not in ("E1", "E2"):
        # core 只有 E3/E4：无 E1/E2 支撑，不足以 grounded
        return "ungrounded"
    return "grounded"


def _validity_decision(votes: list[tuple[str, str | None]]) -> str:
    """返回 accepted / rejected / disputed / insufficient / need_human。"""
    effective = [v for v in votes if v[0] != "not_assessed"]
    if len(effective) < 2:
        return "need_human"  # docs/12 §4 顺序 1、§6 每候选有效票 <2
    accept = sum(1 for v in effective if v[0] == "accept")
    reject = sum(1 for v in effective if v[0] == "reject")
    if accept >= 2 and reject < 2:
        return "accepted"
    if reject >= 2:
        return "rejected"
    if len(effective) == 2 and accept == 1 and reject == 0:
        return "insufficient"
    if len(effective) == 2 and accept == 0 and reject == 1:
        return "insufficient"
    return "disputed"


def _severity_decision(
    votes: list[tuple[str, str | None]],
) -> tuple[str, str | None, bool]:
    """只在 validity=accepted 时调用；返回 (状态, 严重级, 是否暂定)。"""
    accepted = [v for v in votes if v[0] == "accept"]
    present = [v[1] for v in accepted if v[1] is not None]
    if not present:
        return "missing", None, False
    ranks = [SEVERITY_ORDER[s] for s in present]  # type: ignore[index]
    if max(ranks) - min(ranks) >= 2:
        return "severity_disputed", None, False
    severity = SEVERITY_STATES[max(ranks)]
    provisional = (max(ranks) - min(ranks) == 1) or len(present) < len(accepted)
    if severity == "blocker" and len(present) < len(accepted):
        # blocker 不能基于缺失严重级的 accept 票成立
        return "missing", None, provisional
    return "ok", severity, provisional


def _issue_status(issue: dict[str, Any], participants: int) -> dict[str, Any]:
    label = issue.get("candidate_id", "?")
    votes = _norm_votes(issue.get("votes"), participants, label)
    claims = _norm_claims(issue.get("claims"), label)

    if claims is not None:
        evidence_status = aggregate_claim_evidence(claims)
    else:
        evidence_status = issue.get("evidence_status", "ungrounded")
        if evidence_status not in EVIDENCE_STATUS:
            raise VerdictInputError(f"{label}.evidence_status 非法: {evidence_status!r}")

    trace: dict[str, Any] = {
        "candidate_id": label,
        "evidence_status": evidence_status,
        "validity": None,
        "severity": None,
        "severity_provisional": False,
        "status": "need_human",
        "triggers": [],
    }

    # docs/12 §4 顺序 1：参与数 / 有效票 < 2
    if participants < 2:
        trace["triggers"].append("insufficient_participants")
        return trace
    effective = [v for v in votes if v[0] != "not_assessed"]
    if len(effective) < 2:
        trace["triggers"].append("insufficient_votes")
        return trace

    # 顺序 2：证据冲突
    if evidence_status == "conflicted":
        trace["triggers"].append("evidence_conflict")
        return trace

    validity = _validity_decision(votes)
    trace["validity"] = validity

    # 顺序 3：reject 多数
    if validity == "rejected":
        trace["status"] = "rejected"
        return trace

    # 顺序 4：disputed / insufficient
    if validity == "disputed":
        trace["status"] = "disputed"
        trace["triggers"].append("validity_disputed")
        return trace
    if validity == "insufficient":
        trace["triggers"].append("validity_insufficient")
        return trace

    # 顺序 5：严重级分歧 / 缺失
    severity_state, severity, provisional = _severity_decision(votes)
    trace["severity"] = severity
    trace["severity_provisional"] = provisional
    if severity_state == "severity_disputed":
        trace["triggers"].append("severity_disputed")
        return trace
    if severity_state == "missing":
        trace["triggers"].append("severity_missing")
        return trace

    assert severity is not None
    if severity == "blocker":
        # 顺序 6 + §4.1：blocker 需要 grounded/partially + core E1/E2 supported
        if evidence_status not in ("grounded", "partially_grounded"):
            trace["triggers"].append("blocker_without_evidence")
            return trace
        if claims is not None:
            core = next(c for c in claims if c["role"] == "core")
            if core["status"] != "supported" or core["level"] not in ("E1", "E2"):
                trace["triggers"].append("blocker_core_claim_unsupported")
                return trace
        trace["status"] = "blocker"
        if evidence_status == "partially_grounded":
            trace["triggers"].append("partially_grounded_blocker")
        if participants < 3:
            trace["triggers"].append("blocker_in_partial_review")
        return trace

    # 顺序 7：major / suggestion
    trace["status"] = severity
    return trace


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    """计算一份报告的 AI 结论。

    输入（只读下列字段，其余字段一律忽略）：
      participants: int                 本次评审的席位数 0..3
      issues: list[dict]                每个候选/问题
        candidate_id: str
        votes: list[[validity, severity|null]]
        evidence_status: str            与 claims 二选一
        claims: list[dict]              role/status/level
    输出：
      ai_verdict, issue_statuses, human_review_required, review_completeness,
      arbitration_required, traces
    """
    participants = payload.get("participants")
    if participants not in (0, 1, 2, 3):
        raise VerdictInputError(f"participants 必须是 0..3，实际 {participants!r}")
    raw_issues = payload.get("issues", [])
    if not isinstance(raw_issues, list):
        raise VerdictInputError("issues 必须是数组")
    seen: set[str] = set()
    traces: list[dict[str, Any]] = []
    for issue in raw_issues:
        cid = issue.get("candidate_id")
        if not cid or not isinstance(cid, str):
            raise VerdictInputError("issue.candidate_id 必须是非空字符串")
        if cid in seen:
            raise VerdictInputError(f"candidate_id 重复: {cid}")
        seen.add(cid)
        traces.append(_issue_status(issue, participants))

    statuses = [t["status"] for t in traces]
    issue_statuses = {t["candidate_id"]: t["status"] for t in traces}

    if participants == 0:
        verdict, completeness = None, "failed"
    elif participants == 1:
        verdict, completeness = None, "insufficient"
    else:
        completeness = "full" if participants == 3 else "partial"
        if "blocker" in statuses:
            verdict = "blocked"
        elif any(s in ("disputed", "need_human") for s in statuses):
            verdict = "need_human"
        else:
            verdict = "conditional"

    human_review_required = any(
        t["status"] in ("disputed", "need_human")
        or "partially_grounded_blocker" in t["triggers"]
        or "blocker_in_partial_review" in t["triggers"]
        for t in traces
    )
    arbitration_required = any(
        "validity_disputed" in t["triggers"]
        or "severity_disputed" in t["triggers"]
        or "evidence_conflict" in t["triggers"]
        for t in traces
    )

    return {
        "ai_verdict": verdict,
        "issue_statuses": issue_statuses,
        "human_review_required": human_review_required,
        "review_completeness": completeness,
        "arbitration_required": arbitration_required,
        "traces": traces,
    }


def check_forbidden(output: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    """检查 docs/12 §8 的禁止组合；返回违规描述列表（空 = 合法）。"""
    violations: list[str] = []
    verdict = output["ai_verdict"]
    statuses = list(output["issue_statuses"].values())
    participants = payload["participants"]

    if verdict == "approved":
        violations.append("ai_verdict 不得为 approved")
    if verdict == "blocked" and "blocker" not in statuses:
        violations.append("blocked 但无 blocker 问题")
    if verdict == "conditional" and any(s in ("disputed", "need_human") for s in statuses):
        violations.append("conditional 但存在 disputed/need_human")
    if participants in (0, 1) and verdict is not None:
        violations.append(f"{participants} 席位参与时不得给出正式 ai_verdict")
    if participants in (2, 3) and verdict is None:
        violations.append(f"{participants} 席位参与时不得为空 ai_verdict")
    if any(
        t["status"] == "blocker" and t["evidence_status"] == "ungrounded"
        for t in output["traces"]
    ):
        violations.append("blocker 且 evidence_status=ungrounded")
    return violations
