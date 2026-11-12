"""Build a local candidate artifact for inspection; does not embed, index, publish or call models."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import contract_lib as lib
from app.knowledge.build import build_candidate
from app.knowledge.contract import KnowledgeError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, choices=["current_implementation", "target_specification"])
    parser.add_argument("--source-root", type=Path, help="also verify Git bindings; the archived snapshot is verified offline")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        candidate = build_candidate(lib.ROOT, baseline_type=args.baseline, source_root=args.source_root)
    except (KnowledgeError, OSError) as exc:
        print(f"candidate build failed: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(candidate, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": candidate["status"], "documents": candidate["documents"], "chunks": len(candidate["chunks"]),
        "excluded": len(candidate["excluded_documents"]), "kb_build_version": candidate["kb_build_version"],
        "publication_status": candidate["publication_status"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
