"""Validate candidate knowledge, optionally rechecking immutable MiniShop Git blobs.

Normal mode checks repository integrity; --release additionally fails on unfinished admission work.
Neither mode publishes knowledge or calls a model provider.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import contract_lib as lib
from app.knowledge.audit import audit_repository
from app.knowledge.contract import load_yaml
from contract_lib import Reporter


def run(reporter: Reporter) -> None:
    result = audit_repository(lib.ROOT)
    reporter.checks_run += 1
    for error in result.errors:
        reporter.error("knowledge", "kb_content/", "contract", error)
    for warning in result.warnings:
        reporter.warn("knowledge", "kb_content/", "source", warning)
    contract = load_yaml(lib.ROOT / "design/kb_contract.yaml")
    dictionary = lib.read_lines(lib.DOCS_DIR / "17-全局数据字典.md")
    for key, values in contract["governance_enums"].items():
        documented = lib.dictionary_enum(dictionary, f"knowledge_governance.{key}")
        if documented is None or set(documented) != set(values):
            reporter.error("knowledge", "docs/17-全局数据字典.md", key, "治理枚举与机器契约不一致")
    baseline_types = lib.dictionary_enum(dictionary, "review_baseline.type")
    if set(baseline_types or []) != set(contract["baseline_types"]):
        reporter.error("knowledge", "docs/17-全局数据字典.md", "review_baseline.type", "与机器契约不一致")
    spec = lib.read_lines(lib.ROOT / "TestJury_项目知识库数据规范_v1.0.md")
    mapping = {row[0].strip("`"): row[1].strip("`") for _, row in lib.md_table_rows(spec, "内容知识类型")}
    if mapping != contract["knowledge_type_mapping"]:
        reporter.error("knowledge", "design/kb_contract.yaml", "knowledge_type_mapping", "与项目规范类型映射表不一致")
    reporter.note(f"{len(result.documents)} documents; {len(set(result.release_blockers))} formal release blockers; "
                  "offline content audit, runtime activation not queried")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, help="read-only MiniShop repository containing the bound commit")
    parser.add_argument("--release", action="store_true", help="also reject all remaining publication blockers")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = audit_repository(lib.ROOT, source_root=args.source_root)
    payload = result.payload()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for key in ("documents", "content_statuses", "source_counts", "snapshot_verified", "repository_verified", "manual_review_verified", "release_ready"):
            print(f"{key}: {payload[key]}")
        for label, messages in (("ERROR", result.errors), ("WARN", result.warnings), ("BLOCKED", payload["release_blockers"])):
            for message in messages:
                print(f"[{label}] {message}")
    return int(bool(result.errors or (args.release and result.release_blockers)))


if __name__ == "__main__":
    raise SystemExit(main())
