#!/usr/bin/env python
"""契约检查聚合入口（CI 唯一入口）。

用法：
    python scripts/check_contracts.py            # 全部检查
    python scripts/check_contracts.py --list     # 列出检查模块
    python scripts/check_contracts.py --only docs,verdict-cases
    python scripts/check_contracts.py --json     # 机器可读输出

环境变量：
    TJ_REPO_ROOT  检查另一个仓库副本（用于变异测试，见 ACC-M0-017）

退出码：0 = 全部通过；1 = 存在错误。
每条错误输出 `[检查项] 文件:行 | 规则/字段 | 期望与实际`，便于 CI 直接定位。
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_docs
import check_m0_acceptance
import check_rubric
import check_verdict_cases
import contract_lib as lib
from contract_lib import Reporter

CHECKS = [
    ("docs", "跨文档枚举、幂等口径、决策索引、文档索引与路径", check_docs.run),
    ("rubric", "Rubric Schema/业务约束/冻结副本/Prompt 引用", check_rubric.run),
    ("verdict-cases", "Verdict 真值表用例、规则覆盖与属性不变量", check_verdict_cases.run),
    ("m0-acceptance", "M0 退出条件与契约清理用例的覆盖和追踪字段", check_m0_acceptance.run),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="TestJury 契约检查聚合入口")
    parser.add_argument("--list", action="store_true", help="列出检查模块")
    parser.add_argument("--only", default="", help="只运行指定模块（逗号分隔）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()

    if args.list:
        for name, description, _ in CHECKS:
            print(f"{name:14s} {description}")
        return 0

    selected = {item.strip() for item in args.only.split(",") if item.strip()}
    unknown = selected - {name for name, _, _ in CHECKS}
    if unknown:
        print(f"未知检查模块: {sorted(unknown)}", file=sys.stderr)
        return 1

    reporter = Reporter()
    for name, description, runner in CHECKS:
        if selected and name not in selected:
            continue
        sub = Reporter()
        try:
            runner(sub)
        except Exception:  # noqa: BLE001 - 检查器崩溃必须成为 CI 失败而不是静默跳过
            sub.error(name, "<internal>", "crash", traceback.format_exc(limit=3))
        reporter.findings.extend(sub.findings)
        reporter.checks_run += sub.checks_run
        reporter.notes.extend(f"{name}: {note}" for note in sub.notes)
        if not args.json:
            print(f"-- {name}: {'失败' if not sub.ok() else '通过'}（{len(sub.errors)} 错误）")

    if args.json:
        payload = {
            "ok": reporter.ok(),
            "checks_run": reporter.checks_run,
            "notes": reporter.notes,
            "findings": [
                {
                    "severity": item.severity,
                    "check": item.check,
                    "file": item.file,
                    "line": item.line,
                    "item": item.item,
                    "message": item.message,
                }
                for item in reporter.findings
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if reporter.ok() else 1

    print()
    for note in reporter.notes:
        print(f"[NOTE] {note}")
    for finding in reporter.findings:
        print(finding.render())

    errors = len(reporter.errors)
    warnings = len(reporter.warnings)
    if errors:
        print(f"\n结果: 失败（{reporter.checks_run} 项检查，{errors} 个错误，{warnings} 个警告）")
        return 1
    print(f"\n结果: 通过（{reporter.checks_run} 项检查，{warnings} 个警告）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
