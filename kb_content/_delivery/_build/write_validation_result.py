import json, os
p = r"kb_content\_delivery\_build\audit_2026-11-12.json"
d = json.load(open(p, encoding="utf-8"))
c = d["counts"]
out = {"summary": {"documents": c["docs"], "ids": c["ids"], "governance_ids": c["governance_ids"],
                   "anchor_checks": c["anchors"], "by_type": c["by_type"], "by_status": c["by_status"],
                   "by_evidence": c["by_evidence"], "errors": c["errors"], "warnings": c["warnings"],
                   "drift": c["drift"], "snapshot_after_review": "2026-11-12"},
       "errors": d["meta_errors"], "warnings": d["meta_warnings"], "drift": d["drift"]}
json.dump(out, open(r"kb_content\_delivery\validation_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("updated validation_result.json", out["summary"])
