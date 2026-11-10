"""检查 Verdict 可执行真值表：结构、覆盖度、参考判定器一致性、属性不变量。

对应 docs/28 §5（P0-4）与 docs/12。
失败时输出文件、用例 ID、规则 ID、期望/实际。
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_lib as lib
from contract_lib import Reporter, rel
from verdict_reference import (
    CLAIM_LEVELS,
    CLAIM_ROLES,
    CLAIM_STATUS,
    EVIDENCE_STATUS,
    ISSUE_STATUSES,
    SEVERITY_STATES,
    VALIDITY_STATES,
    VerdictInputError,
    check_forbidden,
    evaluate,
)

CASES_PATH = lib.DESIGN_DIR / "verdict_cases.yaml"
CHECK = "verdict-cases"
KINDS = {"positive", "negative", "boundary", "property", "invalid"}
REQUIRED_CASE_KEYS = {"id", "rule", "kind", "description", "input", "expected"}
REQUIRED_EXPECT_KEYS = {
    "ai_verdict",
    "issue_statuses",
    "human_review_required",
    "review_completeness",
    "arbitration_required",
}
TRUTH_TABLE_SECTIONS = ("§2", "§3", "§4", "§5")


def _check_registry(data: dict[str, Any], reporter: Reporter) -> tuple[dict[str, str], set[str]]:
    rules: dict[str, str] = {}
    for index, rule in enumerate(data.get("rules", [])):
        rid = rule.get("id")
        if not rid:
            reporter.error(CHECK, rel(CASES_PATH), f"rules[{index}]", "缺少 id")
            continue
        if rid in rules:
            reporter.error(CHECK, rel(CASES_PATH), f"rule {rid}", "规则 ID 重复")
        rules[rid] = rule.get("doc", "")
        if not rule.get("doc"):
            reporter.error(CHECK, rel(CASES_PATH), f"rule {rid}", "缺少 doc 引用")

    invariants = {inv.get("id") for inv in data.get("invariants", []) if inv.get("id")}
    for expected in (f"I{i}" for i in range(1, 9)):
        if expected not in invariants:
            reporter.error(CHECK, rel(CASES_PATH), expected, "缺少不变量定义（docs/12 §4、docs/28 §5.2 要求 I1–I8）")
    return rules, invariants


def _check_case_shape(case: dict[str, Any], rules: dict[str, str], reporter: Reporter) -> str:
    cid = case.get("id", "<missing-id>")
    missing = REQUIRED_CASE_KEYS - set(case)
    if missing:
        reporter.error(CHECK, rel(CASES_PATH), cid, f"缺少字段: {sorted(missing)}")
    if case.get("rule") not in rules:
        reporter.error(CHECK, rel(CASES_PATH), cid, f"引用未登记规则: {case.get('rule')!r}")
    kind = case.get("kind")
    if kind not in KINDS:
        reporter.error(CHECK, rel(CASES_PATH), cid, f"kind 非法: {kind!r}（允许 {sorted(KINDS)}）")
    expected = case.get("expected", {})
    if kind == "invalid":
        if expected.get("error") is not True:
            reporter.error(CHECK, rel(CASES_PATH), cid, "invalid 用例的 expected 必须为 {error: true}")
    else:
        missing_expect = REQUIRED_EXPECT_KEYS - set(expected)
        if missing_expect:
            reporter.error(CHECK, rel(CASES_PATH), cid, f"expected 缺少字段: {sorted(missing_expect)}")
    return cid


def _compare(cid: str, rule: str, expected: dict[str, Any], output: dict[str, Any], reporter: Reporter) -> None:
    for key in REQUIRED_EXPECT_KEYS:
        if key not in expected:
            continue
        want = expected[key]
        got = output.get(key)
        if want != got:
            reporter.error(
                CHECK,
                rel(CASES_PATH),
                f"{cid}[{rule}].{key}",
                f"期望 {want!r}，实际 {got!r}",
            )


def _check_cases(data: dict[str, Any], rules: dict[str, str], reporter: Reporter) -> list[dict[str, Any]]:
    cases = data.get("cases", [])
    if not isinstance(cases, list) or not cases:
        reporter.error(CHECK, rel(CASES_PATH), "cases", "用例列表为空")
        return []
    seen: set[str] = set()
    used_rules: set[str] = set()
    kinds_seen: set[str] = set()
    for case in cases:
        cid = _check_case_shape(case, rules, reporter)
        if cid in seen:
            reporter.error(CHECK, rel(CASES_PATH), cid, "用例 ID 重复")
        seen.add(cid)
        used_rules.add(case.get("rule"))
        kinds_seen.add(case.get("kind"))

        payload = case.get("input", {})
        try:
            output = evaluate(payload)
        except VerdictInputError as exc:
            if case.get("kind") != "invalid":
                reporter.error(CHECK, rel(CASES_PATH), cid, f"参考判定器拒绝合法用例: {exc}")
            continue
        if case.get("kind") == "invalid":
            reporter.error(CHECK, rel(CASES_PATH), cid, "非法输入未被参考判定器拒绝")
            continue

        _compare(cid, str(case.get("rule")), case.get("expected", {}), output, reporter)
        for violation in check_forbidden(output, payload):
            reporter.error(CHECK, rel(CASES_PATH), cid, f"命中禁止组合: {violation}")

    for rid in rules:
        if rid not in used_rules:
            reporter.error(CHECK, rel(CASES_PATH), f"rule {rid}", "规则未被任何用例覆盖")
    for kind in KINDS:
        if kind not in kinds_seen:
            reporter.error(CHECK, rel(CASES_PATH), "kinds", f"缺少 {kind} 类用例")
    for section in TRUTH_TABLE_SECTIONS:
        if not any(section in rules.get(case.get("rule"), "") for case in cases):
            reporter.error(CHECK, rel(CASES_PATH), section, f"真值表 {section} 未被任何用例覆盖")
    return cases


def _check_forbidden(data: dict[str, Any], reporter: Reporter) -> None:
    entries = data.get("forbidden", [])
    expected = {
        "blocked_without_blocker",
        "conditional_with_dispute",
        "approved",
        "formal_verdict_without_enough_participants",
        "blocker_without_evidence",
    }
    names = {entry.get("name") for entry in entries}
    missing = expected - names
    if missing:
        reporter.error(CHECK, rel(CASES_PATH), "forbidden", f"缺少禁止组合: {sorted(missing)}")
    ids = [entry.get("id") for entry in entries]
    if len(ids) != len(set(ids)):
        reporter.error(CHECK, rel(CASES_PATH), "forbidden", "禁止组合 ID 重复")


# ────────────────────────── 属性测试 ──────────────────────────


def _random_votes(rng: random.Random, participants: int) -> list[list[Any]]:
    votes: list[list[Any]] = []
    for _ in range(participants):
        validity = rng.choice(VALIDITY_STATES)
        if validity == "accept":
            severity = rng.choice(list(SEVERITY_STATES) + [None])
        else:
            severity = None
        votes.append([validity, severity])
    return votes


def _issue(rng: random.Random, participants: int, cid: str = "C1") -> dict[str, Any]:
    issue: dict[str, Any] = {
        "candidate_id": cid,
        "votes": _random_votes(rng, participants),
    }
    if rng.random() < 0.35:
        levels = [rng.choice(CLAIM_LEVELS)]
        roles = ["core"] + ["supporting"] * rng.randint(0, 2)
        claims = []
        for role in roles:
            claims.append(
                {
                    "role": role,
                    "status": rng.choice(CLAIM_STATUS),
                    "level": rng.choice(levels + list(CLAIM_LEVELS)),
                }
            )
        # 保证 core 唯一且至少一个 E1/E2 时有确定行为
        issue["claims"] = claims
    else:
        issue["evidence_status"] = rng.choice(EVIDENCE_STATUS)
    return issue


def _run_property_invariant(
    invariant: str,
    rng: random.Random,
    reporter: Reporter,
    iterations: int = 400,
) -> None:
    for index in range(iterations):
        participants = rng.choice([2, 3])
        issue = _issue(rng, participants)
        payload = {"participants": participants, "issues": [issue]}
        output = evaluate(payload)

        if invariant == "I1":
            effective = [v for v in issue["votes"] if v[0] != "not_assessed"]
            if len(effective) < 2:
                if output["issue_statuses"]["C1"] != "need_human":
                    reporter.error(CHECK, rel(CASES_PATH), f"I1#{index}", "有效票 <2 但未判 need_human")
            if "not_assessed" in [v[0] for v in issue["votes"]]:
                if output["issue_statuses"]["C1"] == "rejected" and not any(
                    v[0] == "reject" for v in effective
                ):
                    reporter.error(CHECK, rel(CASES_PATH), f"I1#{index}", "not_assessed 被当成 reject")

        elif invariant == "I2":
            if output["issue_statuses"]["C1"] != "blocker":
                continue
            trace = output["traces"][0]
            if trace["evidence_status"] not in ("grounded", "partially_grounded"):
                reporter.error(CHECK, rel(CASES_PATH), f"I2#{index}", "无 E1/E2 却产出 blocker")
            claims = issue.get("claims")
            if claims:
                core = next(c for c in claims if c["role"] == "core")
                if core["status"] != "supported" or core["level"] not in ("E1", "E2"):
                    reporter.error(CHECK, rel(CASES_PATH), f"I2#{index}", "core 不满足 E1/E2 却产出 blocker")

        elif invariant == "I3":
            mutated = dict(payload, model_claimed_verdict=rng.choice(["approved", "conditional", "blocked", None]))
            if evaluate(mutated)["ai_verdict"] != output["ai_verdict"]:
                reporter.error(CHECK, rel(CASES_PATH), f"I3#{index}", "模型自报结论改变了 ai_verdict")

        elif invariant == "I4":
            mutated = dict(payload, human_status=rng.choice(["approved", "rejected", "changes_requested", "pending"]))
            if evaluate(mutated)["ai_verdict"] != output["ai_verdict"]:
                reporter.error(CHECK, rel(CASES_PATH), f"I4#{index}", "人工状态改变了 ai_verdict")

        elif invariant == "I5":
            others = [_issue(rng, participants, f"C{i}") for i in range(2, rng.randint(2, 4))]
            with_siblings = evaluate({"participants": participants, "issues": [issue] + others})
            if with_siblings["issue_statuses"]["C1"] != output["issue_statuses"]["C1"]:
                reporter.error(CHECK, rel(CASES_PATH), f"I5#{index}", "其他 issue 改变了 C1 的证据判定")

        elif invariant == "I6":
            mutated = dict(
                payload,
                kb_version="kb-1",
                rubric_version="0.1.0",
                prompt_version_hash="p-1",
                model_config_version="m-1",
                embedding_profile_id=1,
            )
            if evaluate(mutated) != output:
                reporter.error(CHECK, rel(CASES_PATH), f"I6#{index}", "版本字段改变了 Verdict 计算")

        elif invariant == "I7":
            if evaluate(payload) != output:
                reporter.error(CHECK, rel(CASES_PATH), f"I7#{index}", "同一输入重复计算结果不一致")
            shuffled = dict(payload)
            votes = list(issue["votes"])
            rng.shuffle(votes)
            shuffled["issues"] = [dict(issue, votes=votes)]
            if evaluate(shuffled)["ai_verdict"] != output["ai_verdict"]:
                reporter.error(CHECK, rel(CASES_PATH), f"I7#{index}", "票序改变了 ai_verdict")

        elif invariant == "I8":
            if output["ai_verdict"] not in ("blocked", "conditional", "need_human", None):
                reporter.error(CHECK, rel(CASES_PATH), f"I8#{index}", f"未知 ai_verdict: {output['ai_verdict']!r}")
            for status in output["issue_statuses"].values():
                if status not in ISSUE_STATUSES:
                    reporter.error(CHECK, rel(CASES_PATH), f"I8#{index}", f"未知 issue 状态: {status!r}")
            if output["review_completeness"] not in ("full", "partial", "insufficient", "failed"):
                reporter.error(CHECK, rel(CASES_PATH), f"I8#{index}", "review_completeness 非法")
            for violation in check_forbidden(output, payload):
                reporter.error(CHECK, rel(CASES_PATH), f"I8#{index}", f"命中禁止组合: {violation}")


def run(reporter: Reporter) -> None:
    reporter.checks_run += 1
    if not CASES_PATH.exists():
        reporter.error(CHECK, rel(CASES_PATH), "file", "文件不存在")
        return
    data = lib.load_yaml(CASES_PATH, reporter, CHECK)
    if not isinstance(data, dict):
        reporter.error(CHECK, rel(CASES_PATH), "root", "顶层必须是对象")
        return

    rules, invariants = _check_registry(data, reporter)
    _check_cases(data, rules, reporter)
    _check_forbidden(data, reporter)

    rng = random.Random(20261110)
    for invariant in sorted(invariants):
        reporter.checks_run += 1
        _run_property_invariant(invariant, rng, reporter)

    reporter.note(
        f"verdict 用例 {len(data.get('cases', []))} 条，规则 {len(rules)} 条，不变量 {len(invariants)} 条，属性抽样 {len(invariants) * 400} 次"
    )


def main() -> int:
    reporter = Reporter()
    run(reporter)
    return lib.print_report(reporter, title="Verdict 用例检查", verbose=True)


if __name__ == "__main__":
    raise SystemExit(main())
