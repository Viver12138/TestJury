"""将人工复核结论回写到治理台账（YAML）。"""
import json, os, datetime, yaml

ROOT = r"C:\Users\Viver\Desktop\综合电商测试平台demo"
KB = os.path.join(ROOT, "kb_content", "minishop", "_governance")
ROWS = json.load(open(os.path.join(ROOT, "kb_content", "_delivery", "_build", "review_input_rows.json"), encoding="utf-8"))
qmap = {x["编号"]: x for x in ROWS["Q"]}
cmap = {x["冲突编号"]: x for x in ROWS["C"]}
gmap = {x["缺口编号"]: x for x in ROWS["G"]}

def d(v):
    if not v:
        return None
    return str(v)[:10]

def yn(v):
    return v == "是"

# --- pending_confirmation ---
p = os.path.join(KB, "pending_confirmation.yaml")
data = yaml.safe_load(open(p, encoding="utf-8"))
for it in data["items"]:
    row = qmap.get(it["id"])
    if not row:
        raise SystemExit("missing Q " + it["id"])
    it["status"] = "answered"
    it["status_cn"] = "已确认"
    it["decision"] = row.get("人工结论")
    it["decision_note"] = row.get("结论说明 / 决策依据")
    it["decided_by"] = row.get("确认人")
    it["decided_at"] = d(row.get("确认日期"))
    it["follow_up"] = row.get("后续动作")
    it["review_note"] = row.get("备注")
    it["applied_at"] = "2026-11-12"
    it["blocking_resolved"] = bool(it.get("blocking"))
data["updated_at"] = "2026-11-12"
data["status"] = "answered"
yaml.safe_dump(data, open(p, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False, width=120)

# --- conflicts ---
p = os.path.join(KB, "conflicts.yaml")
data = yaml.safe_load(open(p, encoding="utf-8"))
resolution_type = {
    "CONFLICT-001": "documented_current_behavior",
    "CONFLICT-002": "accepted_limitation",
    "CONFLICT-003": "doc_fix_pending",
    "CONFLICT-004": "documented_unreachable",
    "CONFLICT-005": "config_fix_pending",
    "CONFLICT-006": "code_fix_pending",
    "CONFLICT-007": "code_fix_pending",
    "CONFLICT-008": "metric_documented",
    "CONFLICT-009": "code_fix_pending",
    "CONFLICT-010": "code_fix_pending",
}
impl_status = {
    "CONFLICT-001": "knowledge_updated_readme_pending",
    "CONFLICT-002": "accepted_limitation_no_code_change",
    "CONFLICT-003": "knowledge_noted_readme_pending",
    "CONFLICT-004": "accepted_current_behavior",
    "CONFLICT-005": "decision_recorded_config_fix_pending",
    "CONFLICT-006": "decision_recorded_code_fix_pending",
    "CONFLICT-007": "decision_recorded_code_fix_pending",
    "CONFLICT-008": "documented_current_metric",
    "CONFLICT-009": "decision_recorded_code_fix_pending",
    "CONFLICT-010": "decision_recorded_code_fix_pending",
}
for c in data["conflicts"]:
    row = cmap.get(c["id"])
    if not row:
        raise SystemExit("missing C " + c["id"])
    c["status"] = "resolved"
    c["resolution"] = row.get("裁决结论")
    c["resolution_type"] = resolution_type.get(c["id"], "decision_recorded")
    c["implementation_status"] = impl_status.get(c["id"], "pending")
    c["decided_by"] = row.get("负责人")
    c["decided_at"] = "2026-11-11"
    c["resolved_at"] = "2026-11-12"
    c["review_note"] = row.get("备注")
data["updated_at"] = "2026-11-12"
data["status"] = "resolved_with_pending_implementation"
yaml.safe_dump(data, open(p, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False, width=120)

# --- knowledge gaps ---
p = os.path.join(KB, "knowledge_gaps.yaml")
data = yaml.safe_load(open(p, encoding="utf-8"))
status_map = {"进行中": "in_progress", "待处理": "open", "已降级": "downgraded", "已关闭": "closed"}
for g in data["gaps"]:
    row = gmap.get(g["id"])
    if not row:
        raise SystemExit("missing GAP " + g["id"])
    g["status"] = status_map.get(row.get("当前状态"), "open")
    g["status_cn"] = row.get("当前状态")
    g["owner_role"] = row.get("建议补充人角色")
    g["resolution_plan"] = row.get("补充计划 / 负责人")
    g["due_date"] = d(row.get("完成日期"))
    g["review_note"] = row.get("备注")
    g["updated_at"] = "2026-11-12"
data["updated_at"] = "2026-11-12"
yaml.safe_dump(data, open(p, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False, width=120)

print("updated pending/conflicts/gaps")
print("Q:", len(data.get("gaps", [])), "| conflicts resolved:", len(yaml.safe_load(open(os.path.join(KB, "conflicts.yaml"), encoding="utf-8"))["conflicts"]))
