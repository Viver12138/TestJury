"""执行与验收证据台账检查（补充 16 / docs/30）。

校验 design/execution_plan.yaml 与 decisions.yaml、docs/08 §2.16、模型准入/实验协议/
知识库试点/复核责任表的一致性；accepted 状态必须有验收证据。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_lib as lib
from contract_lib import Reporter, rel

CHECK = "execution-plan"
PLAN = lib.DESIGN_DIR / "execution_plan.yaml"
DECISIONS = lib.DESIGN_DIR / "decisions.yaml"
DOCS08 = lib.DOCS_DIR / "08-评审修订与实施计划.md"
ADMISSION = lib.DESIGN_DIR / "model_admission.yaml"
PROTOCOL = lib.DESIGN_DIR / "experiment_protocol.yaml"
KB_PILOT = lib.DESIGN_DIR / "kb_pilot.yaml"
ROSTER = lib.DESIGN_DIR / "review_roster.yaml"

STATUS_MODEL = ("designed", "implemented", "verified", "accepted")
PHASES = {"M0", "M1", "M2", "M3", "M4", "M5", "M6", "production"}
ADMISSION_STATUS = {"unverified", "testing", "verified", "deprecated"}
DATA_ADMISSION = {"pending", "approved", "approved_with_masking", "rejected"}
PROTOCOL_STATUS = {"draft", "signed", "running", "completed"}
KB_STATUS = {"proposed", "selected", "piloting", "accepted"}


def _require_fields(item: dict[str, Any], fields: tuple[str, ...], label: str, reporter: Reporter, path: Path) -> None:
    missing = [field for field in fields if field not in item]
    if missing:
        reporter.error(CHECK, rel(path), label, f"缺少字段: {missing}")


def _check_stage_mapping(plan: dict[str, Any], reporter: Reporter) -> None:
    mapping = plan.get("stage_mapping", {})
    gates = plan.get("stage_gates", {})
    allowed_required = {"owner_assigned", "decision_recorded", "implemented", "verified", "accepted"}
    for stage in ("S1", "S2", "S3", "S4"):
        spec = mapping.get(stage)
        if not isinstance(spec, dict):
            reporter.error(CHECK, rel(PLAN), f"stage_mapping.{stage}", "缺少阶段定义")
            continue
        if not spec.get("milestones") or not spec.get("requires"):
            reporter.error(CHECK, rel(PLAN), f"stage_mapping.{stage}", "必须有里程碑与必需项")
        stage_gates = gates.get(stage)
        if not isinstance(stage_gates, dict):
            reporter.error(CHECK, rel(PLAN), f"stage_gates.{stage}", "缺少最低状态门槛")
            continue
        if set(stage_gates) != set(spec.get("requires", [])):
            reporter.error(CHECK, rel(PLAN), f"stage_gates.{stage}", "与 stage_mapping.requires 项目集合不一致")
        for item_id, required in stage_gates.items():
            if required not in allowed_required:
                reporter.error(CHECK, rel(PLAN), f"stage_gates.{stage}.{item_id}", f"未知最低状态 {required!r}")
    s2 = mapping.get("S2", {}).get("requires", [])
    if "V-03" in s2 or "V-03A" in s2 or "V-03B" in s2:
        reporter.error(CHECK, rel(PLAN), "stage_mapping.S2", "S2 不得要求 Rubric 效果/生产发布（V-03A/V-03B）")
    lifecycle = plan.get("rubric_lifecycle", {})
    for key in ("M0", "M2_M6", "production"):
        if not lifecycle.get(key):
            reporter.error(CHECK, rel(PLAN), f"rubric_lifecycle.{key}", "缺少 Rubric 生命周期要求")
    transitions = plan.get("state_transitions", [])
    pairs = {(item.get("from"), item.get("to")) for item in transitions}
    for required in (("designed", "implemented"), ("implemented", "verified"), ("verified", "accepted"),
                     ("verified", "implemented"), ("accepted", "implemented"), ("accepted", "verified")):
        if required not in pairs:
            reporter.error(CHECK, rel(PLAN), "state_transitions", f"缺少转换 {required[0]} → {required[1]}")

    readme = lib.read_text(lib.ROOT / "README.md")
    match = re.search(r"\*\*状态\*\*：\*\*(design-v\d+\.\d+)", readme)
    baseline = plan.get("baseline")
    current = match.group(1) if match else None
    for path in sorted(lib.DESIGN_DIR.glob("*.yaml")):
        data = lib.load_yaml(path, reporter, CHECK)
        value = data.get("baseline") if isinstance(data, dict) else None
        if isinstance(value, str) and value.startswith("design-v") and current and value != current:
            reporter.error(CHECK, rel(path), "baseline", f"与 README 设计基线不一致：{value} vs {current}")


def _check_plan(plan: dict[str, Any], decisions: dict[str, Any], reporter: Reporter) -> None:
    if plan.get("status_model") != list(STATUS_MODEL):
        reporter.error(CHECK, rel(PLAN), "status_model", f"必须为 {list(STATUS_MODEL)}")

    open_q = {item.get("id") for item in decisions.get("open_questions", []) if item.get("status") == "open"}
    plan_q = [item.get("id") for item in plan.get("open_items", [])]
    if set(plan_q) != open_q:
        reporter.error(
            CHECK,
            rel(PLAN),
            "open_items",
            f"与 decisions.yaml 的 open 待决项不一致：缺少 {sorted(open_q - set(plan_q))}，多出 {sorted(set(plan_q) - open_q)}",
        )
    if len(plan_q) != len(set(plan_q)):
        reporter.error(CHECK, rel(PLAN), "open_items", "待决项 ID 重复")

    for item in plan.get("open_items", []):
        qid = item.get("id")
        _require_fields(item, ("id", "title", "status", "owner", "phase", "blocking", "next_action", "evidence"), qid, reporter, PLAN)
        if item.get("phase") not in PHASES:
            reporter.error(CHECK, rel(PLAN), f"{qid}.phase", f"非法阶段 {item.get('phase')!r}")
        if not item.get("blocking"):
            reporter.error(CHECK, rel(PLAN), f"{qid}.blocking", "必须声明阻塞阶段")
        if not item.get("evidence"):
            reporter.error(CHECK, rel(PLAN), f"{qid}.evidence", "必须声明所需证据")

    mapping = plan.get("stage_mapping", {})
    stage_of: dict[str, str] = {}
    for stage, spec in mapping.items():
        for item_id in spec.get("requires", []):
            stage_of[str(item_id)] = stage
    all_items = {str(item.get("id")): item for group in ("open_items", "verification_items") for item in plan.get(group, [])}
    for item_id, stage in stage_of.items():
        item = all_items.get(item_id, {})
        if stage in ("S1", "S2", "S3") and item.get("phase") == "production":
            reporter.error(CHECK, rel(PLAN), f"{item_id}.phase", f"{stage} 前置阶段不能要求 production 阶段的项")
        if stage == "S4" and item.get("phase") != "production" and item_id.startswith("V-"):
            reporter.error(CHECK, rel(PLAN), f"{item_id}.phase", "S4 只能要求 production 阶段的验证项")

    decision_ids = {str(item.get("id")): item for item in decisions.get("decisions", [])}
    for item in plan.get("open_items", []):
        ref = item.get("decision_ref")
        if ref:
            decision = decision_ids.get(str(ref))
            if decision is None:
                reporter.error(CHECK, rel(PLAN), f"{item.get('id')}.decision_ref", f"决策 {ref} 不存在")
            elif decision.get("status") != "decided":
                reporter.error(CHECK, rel(PLAN), f"{item.get('id')}.decision_ref", f"决策 {ref} 未 decided")

    q14 = next((item for item in plan.get("open_items", []) if item.get("id") == "Q-14"), None)
    if not q14:
        reporter.error(CHECK, rel(PLAN), "Q-14", "缺少 Q-14")
    else:
        if q14.get("phase") != "M2":
            reporter.error(CHECK, rel(PLAN), "Q-14.phase", "Q-14 应为 M2（协议签署），实验执行归 V-06")
        evidence = set(q14.get("evidence") or [])
        if not {"signed_protocol", "protocol_review_record"} <= evidence:
            reporter.error(CHECK, rel(PLAN), "Q-14.evidence", "Q-14 只负责协议签署类证据")
        if {"experiment_report", "topology_decision"} & evidence:
            reporter.error(CHECK, rel(PLAN), "Q-14.evidence", "实验报告/拓扑决策应归 V-06")
        if plan.get("stage_mapping", {}).get("S2", {}).get("protocol") != "Q-14":
            reporter.error(CHECK, rel(PLAN), "S2.protocol", "S2 协议门禁必须引用 Q-14")
    v06 = next((item for item in plan.get("verification_items", []) if item.get("id") == "V-06"), None)
    if v06 and not {"experiment_report", "topology_decision"} <= set(v06.get("evidence") or []):
        reporter.error(CHECK, rel(PLAN), "V-06.evidence", "V-06 必须负责实验报告与拓扑决策")

    deps = plan.get("version_dependencies", {})
    expected_dep_items = {item.get("id") for item in plan.get("verification_items", [])}
    if set(deps) != expected_dep_items:
        reporter.error(CHECK, rel(PLAN), "version_dependencies", "必须为每个验证项声明版本依赖")
    allowed_deps = {"design", "code_commit", "rubric", "report_schema", "model_config", "prompt", "dataset", "kb", "embedding_profile", "adapter"}
    for item_id, keys in deps.items():
        unknown = sorted(set(keys) - allowed_deps)
        if unknown:
            reporter.error(CHECK, rel(PLAN), f"version_dependencies.{item_id}", f"未知版本键 {unknown}")

    expected_v = ["V-01", "V-02", "V-03A", "V-03B", "V-04", "V-05", "V-06", "V-07", "V-08", "V-09", "V-10", "V-11", "V-12"]
    actual_v = [item.get("id") for item in plan.get("verification_items", [])]
    if actual_v != expected_v:
        reporter.error(CHECK, rel(PLAN), "verification_items", f"必须包含 V-01/V-02/V-03A/V-03B/V-04–V-12 且顺序一致，实际 {actual_v}")
    for item in plan.get("verification_items", []):
        vid = item.get("id")
        _require_fields(item, ("id", "title", "status", "owner", "phase", "blocking", "evidence"), vid, reporter, PLAN)
        if item.get("status") not in STATUS_MODEL:
            reporter.error(CHECK, rel(PLAN), f"{vid}.status", f"非法状态 {item.get('status')!r}")
        if item.get("phase") not in PHASES:
            reporter.error(CHECK, rel(PLAN), f"{vid}.phase", f"非法阶段 {item.get('phase')!r}")
        if item.get("status") == "accepted":
            for field in ("acceptance_evidence", "acceptance_by", "acceptance_at"):
                if not item.get(field):
                    reporter.error(CHECK, rel(PLAN), f"{vid}.{field}", "accepted 必须有验收证据/验收人/时间")
        if item.get("status") in ("implemented", "verified") and not item.get("evidence"):
            reporter.error(CHECK, rel(PLAN), f"{vid}.evidence", "进入 implemented/verified 必须有证据")
    reporter.note(f"执行台账：open 待决 {len(plan_q)} 项，验证项 {len(actual_v)} 项")


def _check_admission(data: dict[str, Any], reporter: Reporter) -> None:
    roles = data.get("roles", [])
    expected = {"chief_blind", "chief_vote", "arbitration", "jury_a", "jury_b", "preprocess", "embedding", "rerank"}
    actual = {role.get("role") for role in roles}
    if actual != expected:
        reporter.error(CHECK, rel(ADMISSION), "roles", f"角色集合不一致：缺少 {sorted(expected - actual)}，多出 {sorted(actual - expected)}")
    for role in roles:
        rid = role.get("role")
        if role.get("verification_status") not in ADMISSION_STATUS:
            reporter.error(CHECK, rel(ADMISSION), f"{rid}.verification_status", f"非法状态 {role.get('verification_status')!r}")
        if role.get("data_admission_status") not in DATA_ADMISSION:
            reporter.error(CHECK, rel(ADMISSION), f"{rid}.data_admission_status", f"非法状态 {role.get('data_admission_status')!r}")
        if role.get("verification_status") == "verified":
            for field in ("real_model_id", "evidence", "reviewer"):
                if not role.get(field):
                    reporter.error(CHECK, rel(ADMISSION), f"{rid}.{field}", "verified 必须有真实 ID/证据/审核人")
        if role.get("data_admission_status") in ("approved", "approved_with_masking"):
            if role.get("allowed_data_level") is None or role.get("dpa_signed") is not True:
                reporter.error(CHECK, rel(ADMISSION), f"{rid}.data_admission", "approved 必须有允许数据等级与 DPA")


def _check_protocol(data: dict[str, Any], reporter: Reporter) -> None:
    status = data.get("status")
    if status not in PROTOCOL_STATUS:
        reporter.error(CHECK, rel(PROTOCOL), "status", f"非法状态 {status!r}")
        return
    if status == "draft":
        return
    if not data.get("dataset_version"):
        reporter.error(CHECK, rel(PROTOCOL), "dataset_version", f"{status} 前必须冻结数据集")
    for field in ("signed_by", "signed_at"):
        if not data.get(field):
            reporter.error(CHECK, rel(PROTOCOL), field, f"{status} 前必须签署")
    thresholds = data.get("thresholds", {})
    for field in ("strict_blocker_recall_min_abs_gain", "fdr_max_abs_increase", "cost_per_valid_issue_max_ratio", "p95_latency_max_ratio"):
        if thresholds.get(field) is None:
            reporter.error(CHECK, rel(PROTOCOL), f"thresholds.{field}", f"{status} 前必须填具体阈值（不能实验后选口径）")
    stats = data.get("statistical_design", {})
    for field in (
        "alpha",
        "power",
        "pairing",
        "ci_method",
        "bootstrap_iterations",
        "multiple_comparison",
        "min_blocker_events_per_group",
        "min_samples_per_stratum",
        "random_seed",
        "repeats_per_case",
        "aggregation_method",
        "mde_strict_blocker_recall_gain",
        "baseline_blocker_rate",
        "sample_size_method",
        "bootstrap_unit",
        "clustering_unit",
        "primary_hypotheses",
        "abnormal_sample_policy",
        "stopping_rule",
    ):
        if field == "primary_hypotheses":
            if not stats.get(field):
                reporter.error(CHECK, rel(PROTOCOL), f"statistical_design.{field}", f"{status} 前必须冻结主假设集合")
        elif stats.get(field) is None:
            reporter.error(CHECK, rel(PROTOCOL), f"statistical_design.{field}", f"{status} 前必须冻结统计设计")


def _check_kb_pilot(data: dict[str, Any], reporter: Reporter) -> None:
    modules = data.get("modules", [])
    if not 1 <= len(modules) <= 5:
        reporter.error(CHECK, rel(KB_PILOT), "modules", f"先行试点允许 1–5 个模块，实际 {len(modules)}")
    project_id = data.get("project_id")
    registry = lib.ROOT / "kb_content" / str(project_id) / "project" / "modules.yaml"
    if not project_id or not registry.is_file():
        reporter.error(CHECK, rel(KB_PILOT), "project_id", "必须引用已登记的项目模块清单")
        return
    registered = {item.get("id") for item in lib.load_yaml(registry)["modules"]}
    module_ids = [module.get("module_id") for module in modules]
    if len(set(module_ids)) != len(module_ids) or not set(module_ids) <= registered:
        reporter.error(CHECK, rel(KB_PILOT), "module_id", "试点模块必须唯一且属于当前项目白名单")
    orders = [module.get("pilot_order") for module in modules]
    if len(orders) != len(set(orders)):
        reporter.error(CHECK, rel(KB_PILOT), "pilot_order", "试点顺序重复")
    piloting = [module for module in modules if module.get("status") == "piloting"]
    if len(piloting) > 1:
        reporter.error(CHECK, rel(KB_PILOT), "status", "同一时刻最多一个 piloting 模块")
    for module in modules:
        mid = module.get("module_id")
        if module.get("status") not in KB_STATUS:
            reporter.error(CHECK, rel(KB_PILOT), f"{mid}.status", f"非法状态 {module.get('status')!r}")
        if module.get("status") in ("selected", "piloting", "accepted"):
            for field in ("module_owner", "kb_creator", "kb_reviewer", "acceptance_dataset"):
                if not module.get(field):
                    reporter.error(CHECK, rel(KB_PILOT), f"{mid}.{field}", f"{module.get('status')} 必须指定")
            if not module.get("source_inventory"):
                reporter.error(CHECK, rel(KB_PILOT), f"{mid}.source_inventory", f"{module.get('status')} 必须有来源清单")
            if not module.get("expected_rule_count") or not module.get("case_count"):
                reporter.error(CHECK, rel(KB_PILOT), f"{mid}.counts", f"{module.get('status')} 必须有规则数与用例数")


def _check_roster(data: dict[str, Any], pilot: dict[str, Any], reporter: Reporter) -> None:
    ready = data.get("status") == "ready"
    if data.get("status") not in ("pending", "ready"):
        reporter.error(CHECK, rel(ROSTER), "status", f"非法状态 {data.get('status')!r}")
    pilot_ids = {module.get("module_id") for module in pilot.get("modules", [])}
    roster_ids = {module.get("module_id") for module in data.get("modules", [])}
    if data.get("project_id") != pilot.get("project_id"):
        reporter.error(CHECK, rel(ROSTER), "project_id", "必须与 kb_pilot 项目一致")
    if pilot_ids != roster_ids:
        reporter.error(CHECK, rel(ROSTER), "modules", f"模块集合与 kb_pilot 不一致：缺少 {sorted(pilot_ids - roster_ids)}")
    if not ready:
        return
    for module in data.get("modules", []):
        mid = module.get("module_id")
        for field in ("primary_reviewer", "backup_reviewer", "module_owner", "sampler", "arbitrator"):
            if not module.get(field):
                reporter.error(CHECK, rel(ROSTER), f"{mid}.{field}", "status=ready 时必须指定真实人员")


def run(reporter: Reporter) -> None:
    reporter.checks_run += 1
    if not PLAN.exists():
        reporter.error(CHECK, rel(PLAN), "file", "文件不存在")
        return
    plan = lib.load_yaml(PLAN, reporter, CHECK)
    decisions = lib.load_yaml(DECISIONS, reporter, CHECK)
    if not isinstance(plan, dict) or not isinstance(decisions, dict):
        reporter.error(CHECK, rel(PLAN), "root", "顶层必须是对象")
        return

    _check_plan(plan, decisions, reporter)
    _check_stage_mapping(plan, reporter)

    reporter.checks_run += 1
    admission = lib.load_yaml(ADMISSION, reporter, CHECK)
    if isinstance(admission, dict):
        _check_admission(admission, reporter)

    reporter.checks_run += 1
    protocol = lib.load_yaml(PROTOCOL, reporter, CHECK)
    if isinstance(protocol, dict):
        _check_protocol(protocol, reporter)

    reporter.checks_run += 1
    pilot = lib.load_yaml(KB_PILOT, reporter, CHECK)
    if isinstance(pilot, dict):
        _check_kb_pilot(pilot, reporter)

    reporter.checks_run += 1
    roster = lib.load_yaml(ROSTER, reporter, CHECK)
    if isinstance(roster, dict) and isinstance(pilot, dict):
        _check_roster(roster, pilot, reporter)

    doc08 = lib.read_text(DOCS08)
    if "### 2.16 待决事项登记" not in doc08:
        reporter.error(CHECK, rel(DOCS08), "§2.16", "缺少待决事项章节")


def main() -> int:
    reporter = Reporter()
    run(reporter)
    return lib.print_report(reporter, title="执行台账检查", verbose=True)


if __name__ == "__main__":
    raise SystemExit(main())
