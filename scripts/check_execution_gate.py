"""阶段执行门禁（补充 17/18）。

结构检查（check_execution_plan.py）在常规 CI 运行；本脚本在阶段验收/发布门禁运行：
- 按 stage_gates 校验每项最低状态（owner_assigned/decision_recorded/implemented/verified/accepted）；
- 校验证据 manifest（字段、artifact 哈希、validity）；
- 校验状态历史 evidence/<item>/history.jsonl（append-only、与当前状态一致、转换合法）；
- 校验实验协议签署、S4 生产模型数据准入。

用法：python scripts/check_execution_gate.py --stage S2 [--json] [--out path]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_lib as lib
from contract_lib import Reporter, rel

CHECK = "execution-gate"
PLAN = lib.DESIGN_DIR / "execution_plan.yaml"
PROTOCOL = lib.DESIGN_DIR / "experiment_protocol.yaml"
ADMISSION = lib.DESIGN_DIR / "model_admission.yaml"
EVIDENCE_DIR = lib.ROOT / "evidence"

RANK = {"designed": 0, "implemented": 1, "verified": 2, "accepted": 3}


def _items(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for group in ("open_items", "verification_items")
        for item in plan.get(group, [])
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_manifest(item: dict[str, Any], reporter: Reporter) -> None:
    item_id = str(item.get("id"))
    manifest_path = EVIDENCE_DIR / item_id / "manifest.yaml"
    if not manifest_path.exists():
        reporter.error(CHECK, rel(PLAN), f"{item_id}.manifest", f"缺少证据 manifest: evidence/{item_id}/manifest.yaml")
        return
    manifest = lib.load_yaml(manifest_path, reporter, CHECK)
    if not isinstance(manifest, dict):
        reporter.error(CHECK, rel(manifest_path), "manifest", "manifest 必须是对象")
        return
    for field in ("evidence_id", "item_id", "evidence_type", "created_at", "created_by", "versions", "artifact", "validity"):
        if field not in manifest:
            reporter.error(CHECK, rel(manifest_path), field, "manifest 缺少字段")
    if manifest.get("item_id") != item_id:
        reporter.error(CHECK, rel(manifest_path), "item_id", "manifest 的 item_id 与验证项不一致")
    if not manifest.get("versions"):
        reporter.error(CHECK, rel(manifest_path), "versions", "必须绑定版本（代码/模型/数据集等）")
    artifact = manifest.get("artifact", {}) if isinstance(manifest.get("artifact"), dict) else {}
    artifact_path = artifact.get("path")
    if not artifact_path:
        reporter.error(CHECK, rel(manifest_path), "artifact.path", "缺少 artifact 路径")
    else:
        target = (lib.ROOT / artifact_path).resolve()
        if not target.exists():
            reporter.error(CHECK, rel(manifest_path), "artifact.path", f"artifact 不存在: {artifact_path}")
        elif artifact.get("sha256") and _sha256(target) != artifact.get("sha256"):
            reporter.error(CHECK, rel(manifest_path), "artifact.sha256", "artifact 哈希不一致")
    validity = manifest.get("validity", {}) if isinstance(manifest.get("validity"), dict) else {}
    if validity.get("valid") is not True:
        reporter.error(CHECK, rel(manifest_path), "validity.valid", "证据已失效或未声明有效")
    if validity.get("invalidated_by"):
        reporter.error(CHECK, rel(manifest_path), "validity.invalidated_by", "证据标记为已失效")


def _check_history(item: dict[str, Any], plan: dict[str, Any], reporter: Reporter) -> None:
    item_id = str(item.get("id"))
    status = item.get("status")
    history_path = EVIDENCE_DIR / item_id / "history.jsonl"
    if not history_path.exists():
        reporter.error(CHECK, rel(PLAN), f"{item_id}.history", f"缺少状态历史: evidence/{item_id}/history.jsonl")
        return
    allowed = {(entry.get("from"), entry.get("to")) for entry in plan.get("state_transitions", [])}
    entries: list[dict[str, Any]] = []
    for line_no, line in enumerate(history_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            reporter.error(CHECK, rel(history_path), f"line {line_no}", f"JSONL 解析失败: {exc}")
    if not entries:
        reporter.error(CHECK, rel(history_path), "history", "状态历史为空")
        return
    previous = "designed"
    for index, entry in enumerate(entries):
        for field in ("item_id", "from", "to", "at", "actor", "reason", "evidence", "versions"):
            if field not in entry:
                reporter.error(CHECK, rel(history_path), f"{item_id}.history[{index}]", f"缺少字段 {field}")
        if entry.get("item_id") != item_id:
            reporter.error(CHECK, rel(history_path), f"{item_id}.history[{index}].item_id", "与验证项不一致")
        if entry.get("from") != previous:
            reporter.error(CHECK, rel(history_path), f"{item_id}.history[{index}].from", f"应为 {previous}")
        if (entry.get("from"), entry.get("to")) not in allowed:
            reporter.error(CHECK, rel(history_path), f"{item_id}.history[{index}]", "非法状态转换")
        previous = str(entry.get("to"))
    if previous != status:
        reporter.error(CHECK, rel(history_path), f"{item_id}.history", f"历史最后状态 {previous} 与当前 {status} 不一致")


def _check_item(item: dict[str, Any], required: str, plan: dict[str, Any], reporter: Reporter) -> None:
    item_id = str(item.get("id"))
    if not item.get("owner"):
        reporter.error(CHECK, rel(PLAN), f"{item_id}.owner", "阶段门禁要求 owner 非空")
    if required in ("owner_assigned", "decision_recorded"):
        if required == "decision_recorded" and not item.get("decision_ref"):
            reporter.error(CHECK, rel(PLAN), f"{item_id}.decision_ref", "阶段要求已记录决策（decision_ref 非空）")
        return
    if required not in RANK:
        reporter.error(CHECK, rel(PLAN), f"{item_id}.required", f"未知最低状态 {required!r}")
        return
    status = item.get("status")
    if status not in RANK:
        reporter.error(CHECK, rel(PLAN), f"{item_id}.status", f"未知状态 {status!r}")
        return
    if RANK[status] < RANK[required]:
        reporter.error(CHECK, rel(PLAN), f"{item_id}.status", f"阶段要求至少 {required}，当前 {status}")
    if status != "designed":
        _check_manifest(item, reporter)
        _check_history(item, plan, reporter)
    if status == "accepted":
        for field in ("acceptance_evidence", "acceptance_by", "acceptance_at"):
            if not item.get(field):
                reporter.error(CHECK, rel(PLAN), f"{item_id}.{field}", "accepted 必须有验收证据/验收人/时间")


def run(stage: str, reporter: Reporter) -> None:
    plan = lib.load_yaml(PLAN, reporter, CHECK)
    mapping = plan.get("stage_mapping", {}).get(stage)
    gates = plan.get("stage_gates", {}).get(stage)
    if not isinstance(mapping, dict) or not isinstance(gates, dict):
        reporter.error(CHECK, rel(PLAN), stage, "缺少 stage_mapping 或 stage_gates")
        return
    if set(mapping.get("requires", [])) != set(gates):
        reporter.error(CHECK, rel(PLAN), f"{stage}.stage_gates", "stage_gates 与 requires 项目集合不一致")
    items = _items(plan)
    for item_id, required in gates.items():
        item = items.get(item_id)
        if item is None:
            reporter.error(CHECK, rel(PLAN), str(item_id), "阶段要求项不存在")
            continue
        _check_item(item, required, plan, reporter)

    if mapping.get("protocol"):
        protocol = lib.load_yaml(PROTOCOL, reporter, CHECK)
        if protocol.get("status") != "signed":
            reporter.error(CHECK, rel(PROTOCOL), "status", f"{stage} 要求实验协议已签署")
    if stage == "S4":
        admission = lib.load_yaml(ADMISSION, reporter, CHECK)
        for role in admission.get("roles", []):
            if role.get("data_admission_status") not in ("approved", "approved_with_masking"):
                reporter.error(CHECK, rel(ADMISSION), f"{role.get('role')}.data_admission_status", "S4 要求全部生产模型完成数据准入")
    reporter.note(f"阶段 {stage}：检查 {len(gates)} 个必需项（最低状态门槛）")


def main() -> int:
    parser = argparse.ArgumentParser(description="阶段执行门禁")
    parser.add_argument("--stage", required=True, choices=["S1", "S2", "S3", "S4"])
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    parser.add_argument("--out", default="", help="把 JSON 结果写入文件（用于证据归档）")
    args = parser.parse_args()

    reporter = Reporter()
    run(args.stage, reporter)
    payload = {
        "stage": args.stage,
        "ok": reporter.ok(),
        "checks": reporter.checks_run,
        "branch": os.environ.get("GITHUB_REF_NAME"),
        "sha": os.environ.get("GITHUB_SHA"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "findings": [
            {"severity": item.severity, "file": item.file, "item": item.item, "message": item.message}
            for item in reporter.findings
        ],
    }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for note in reporter.notes:
            print(f"[NOTE] {note}")
        for finding in reporter.findings:
            print(finding.render())
        print(f"\n结果: {'通过' if reporter.ok() else '失败'}（{args.stage}）")
    return 0 if reporter.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
