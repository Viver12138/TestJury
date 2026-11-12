"""人工裁决命令行（不代替人工做决定）。

用法：
    python scripts/adjudicate.py list
    python scripts/adjudicate.py show UI-GAME-007
    python scripts/adjudicate.py decide UI-GAME-007 CAND-UI-GAME-007-01 \
        --validity valid --severity blocker --category 状态不自洽 \
        --correction "拆分为启动中/保存中两条用例" --adjudicator 张三
    python scripts/adjudicate.py case-verdict UI-GAME-007 --verdict needs_fix --defect-count 5 --adjudicator 张三
    python scripts/adjudicate.py stats
    python scripts/adjudicate.py export-csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.adjudication import (  # noqa: E402
    AdjudicationError,
    append_history,
    export_csv,
    import_decisions_from_csv,
    load_case,
    record_decision,
    recover_imports,
    save_case,
    set_case_verdict,
    stats,
)

DEFAULT_ROOT = ROOT / "data" / "adjudication"


def _case_path(root: Path, case_id: str) -> Path:
    path = root / f"{case_id}.yaml"
    if not path.exists():
        raise AdjudicationError(f"用例裁决文件不存在: {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="人工裁决工作台")
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出用例与裁决进度")
    show = sub.add_parser("show", help="显示单个用例")
    show.add_argument("case_id")

    decide = sub.add_parser("decide", help="裁决一条候选问题")
    decide.add_argument("case_id")
    decide.add_argument("candidate_id")
    decide.add_argument("--validity", required=True, choices=["valid", "invalid", "uncertain", "needs_spec"])
    decide.add_argument("--severity", choices=["blocker", "major", "suggestion"])
    decide.add_argument("--category")
    decide.add_argument("--correction")
    decide.add_argument("--note")
    decide.add_argument("--adjudicator", required=True)

    verdict = sub.add_parser("case-verdict", help="填写用例级结论")
    verdict.add_argument("case_id")
    verdict.add_argument("--verdict", required=True, choices=["in_progress", "pass", "needs_fix", "blocked", "uncertain"])
    verdict.add_argument("--defect-count", type=int)
    verdict.add_argument("--note")
    verdict.add_argument("--adjudicator", required=True)

    sub.add_parser("stats", help="统计裁决进度")
    sub.add_parser("export-csv", help="导出 adjudication.csv")
    import_csv = sub.add_parser("import-csv", help="把填写好的 CSV 合并回 YAML")
    import_csv.add_argument("--csv", default=str(DEFAULT_ROOT / "adjudication.csv"))
    import_csv.add_argument("--adjudicator", help="CSV 未填 adjudicator 时的默认裁决人")
    import_csv.add_argument("--dry-run", action="store_true", help="只校验，不写库")
    sub.add_parser("recover-imports", help="恢复中断的 CSV 批次导入")

    args = parser.parse_args()
    root = Path(args.root)
    try:
        if args.command == "list":
            for path in sorted(root.glob("*.yaml")):
                data = load_case(path)
                done = sum(
                    1
                    for item in data.get("candidates", [])
                    if item.get("final", {}).get("validity", "pending") != "pending"
                )
                total = len(data.get("candidates", []))
                verdict = data.get("case_level", {}).get("verdict", "pending")
                print(
                    f"{data['case_id']:18} {data.get('case_title', '')[:28]:30} "
                    f"裁决 {done}/{total} 用例结论={verdict}"
                )
            return 0
        if args.command == "show":
            print(yaml_dump(load_case(_case_path(root, args.case_id))))
            return 0
        if args.command == "decide":
            path = _case_path(root, args.case_id)
            data = load_case(path)
            entry = record_decision(
                data,
                args.candidate_id,
                validity=args.validity,
                severity=args.severity,
                category=args.category,
                correction=args.correction,
                adjudicator=args.adjudicator,
                note=args.note,
            )
            save_case(path, data)
            append_history(root / "history.jsonl", entry)
            print(f"已记录：{args.case_id}/{args.candidate_id} -> {args.validity}")
            return 0
        if args.command == "case-verdict":
            path = _case_path(root, args.case_id)
            data = load_case(path)
            entry = set_case_verdict(
                data,
                verdict=args.verdict,
                defect_count=args.defect_count,
                adjudicator=args.adjudicator,
                note=args.note,
            )
            save_case(path, data)
            append_history(root / "history.jsonl", entry)
            print(f"已记录用例结论：{args.case_id} -> {args.verdict}")
            return 0
        if args.command == "stats":
            for key, value in stats(root).items():
                print(f"{key}: {value}")
            return 0
        if args.command == "export-csv":
            count = export_csv(root, root / "adjudication.csv")
            print(f"已导出 {count} 条候选问题到 {root / 'adjudication.csv'}")
            return 0
        if args.command == "import-csv":
            result = import_decisions_from_csv(
                root,
                Path(args.csv),
                default_adjudicator=args.adjudicator,
                dry_run=args.dry_run,
            )
            print(
                f"import-csv: cases={result['cases']} decisions={result['decisions']} "
                f"dry_run={result['dry_run']} "
                f"already_applied={result.get('already_applied', 0)}"
            )
            return 0
        if args.command == "recover-imports":
            result = recover_imports(root)
            print(f"recover-imports: recovered={result['recovered']} failed={result['failed']}")
            return 0
    except AdjudicationError as exc:
        print(f"[ERROR] {exc}")
        return 1
    return 0


def yaml_dump(data):
    import yaml

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


if __name__ == "__main__":
    raise SystemExit(main())
