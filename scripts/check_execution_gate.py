"""阶段执行门禁（补充 17 P0-03）。

结构检查（check_execution_plan.py）在常规 CI 运行；本脚本只在**阶段验收/发布门禁**运行，
检查 owner、实现/验证/验收证据、证据文件是否存在、阶段出口与协议签署状态。

用法：
    python scripts/check_execution_gate.py --stage S2
证据目录约定：evidence/<item_id>/<evidence_id>[.json|.md|...]（见 evidence/README.md）。
"""

from __future__ import annotations

import argparse
import sys
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


def _all_items(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = {}
    for group in ("open_items", "verification_items"):
        for item in plan.get(group, []):
            items[str(item.get("id"))] = item
    return items


def _check_evidence(item: dict[str, Any], field: str, reporter: Reporter, *, required: bool) -> None:
    item_id = str(item.get("id"))
    entries = item.get(field) or []
    if required and not entries:
        reporter.error(CHECK, rel(PLAN), f"{item_id}.{field}", "状态要求必须有证据")
        return
    for entry in entries:
        if not isinstance(entry, str):
            reporter.error(CHECK, rel(PLAN), f"{item_id}.{field}", "证据必须是字符串 ID/路径")
            continue
        base = EVIDENCE_DIR / item_id / entry
        if not (base.exists() or any(base.parent.glob(Path(entry).name + ".*"))):
            reporter.error(CHECK, rel(PLAN), f"{item_id}.{field}", f"证据文件不存在: evidence/{item_id}/{entry}")


def _check_item(item: dict[str, Any], reporter: Reporter) -> None:
    item_id = str(item.get("id"))
    status = item.get("status")
    if not item.get("owner"):
        reporter.error(CHECK, rel(PLAN), f"{item_id}.owner", "阶段门禁要求 owner 非空（不能以'待指定'进入）")
    if status in ("implemented", "verified", "accepted"):
        _check_evidence(item, "evidence", reporter, required=True)
    if status == "accepted":
        for field in ("acceptance_evidence", "acceptance_by", "acceptance_at"):
            if not item.get(field):
                reporter.error(CHECK, rel(PLAN), f"{item_id}.{field}", "accepted 必须有验收证据/验收人/时间")
        _check_evidence(item, "acceptance_evidence", reporter, required=True)


def run(stage: str) -> int:
    reporter = Reporter()
    plan = lib.load_yaml(PLAN, reporter, CHECK)
    if not isinstance(plan, dict):
        return lib.print_report(reporter, title=f"阶段门禁 {stage}")

    mapping = plan.get("stage_mapping", {}).get(stage)
    if not isinstance(mapping, dict):
        reporter.error(CHECK, rel(PLAN), stage, "未定义该阶段")
        return lib.print_report(reporter, title=f"阶段门禁 {stage}")

    items = _all_items(plan)
    for item_id in mapping.get("requires", []):
        item = items.get(item_id)
        if item is None:
            reporter.error(CHECK, rel(PLAN), str(item_id), "阶段要求的项在台账中不存在")
            continue
        _check_item(item, reporter)

    protocol_id = mapping.get("protocol")
    if protocol_id:
        protocol = lib.load_yaml(PROTOCOL, reporter, CHECK)
        if protocol.get("status") != "signed":
            reporter.error(CHECK, rel(PROTOCOL), "status", f"{stage} 要求实验协议已签署（当前 {protocol.get('status')!r}）")

    if stage == "S2":
        # Rubric 只要求可加载；V-03 的 production 发布不属于 S2
        lifecycle = plan.get("rubric_lifecycle", {}).get("M0", [])
        if not lifecycle:
            reporter.error(CHECK, rel(PLAN), "rubric_lifecycle.M0", "缺少 M0 的 Rubric 加载要求")
    if stage == "S4":
        v03 = items.get("V-03", {})
        if v03.get("status") != "accepted":
            reporter.error(CHECK, rel(PLAN), "V-03.status", "S4 要求 Rubric 已验收并发布（accepted）")
        admission = lib.load_yaml(ADMISSION, reporter, CHECK)
        for role in admission.get("roles", []):
            if role.get("data_admission_status") not in ("approved", "approved_with_masking"):
                reporter.error(
                    CHECK,
                    rel(ADMISSION),
                    f"{role.get('role')}.data_admission_status",
                    "S4 要求全部生产模型完成数据准入",
                )

    reporter.note(f"阶段 {stage}：检查 {len(mapping.get('requires', []))} 个必需项")
    return lib.print_report(reporter, title=f"阶段门禁 {stage}")


def main() -> int:
    parser = argparse.ArgumentParser(description="阶段执行门禁")
    parser.add_argument("--stage", required=True, choices=["S1", "S2", "S3", "S4"])
    args = parser.parse_args()
    return run(args.stage)


if __name__ == "__main__":
    raise SystemExit(main())
