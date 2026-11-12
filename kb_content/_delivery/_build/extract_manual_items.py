import os, json, yaml
ROOT = r"C:\Users\Viver\Desktop\综合电商测试平台demo"
KB = os.path.join(ROOT, "kb_content", "minishop")
def load(rel):
    return yaml.safe_load(open(os.path.join(KB, rel), encoding="utf-8"))
questions = load("_governance/pending_confirmation.yaml")["items"]
conflicts = load("_governance/conflicts.yaml")["conflicts"]
gaps = load("_governance/knowledge_gaps.yaml")["gaps"]
docs = []
for dp, dns, fns in os.walk(KB):
    for fn in fns:
        if not fn.endswith(".md") or fn in ("README.md", "release_notes.md"):
            continue
        p = os.path.join(dp, fn)
        text = open(p, encoding="utf-8").read()
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        fm = yaml.safe_load(parts[1])
        if not isinstance(fm, dict) or "id" not in fm:
            continue
        docs.append({
            "id": fm.get("id"), "title": fm.get("title"),
            "knowledge_type": fm.get("knowledge_type"),
            "module_id": fm.get("module_id"),
            "evidence_level": fm.get("evidence_level"),
            "status": fm.get("status"),
            "owner": fm.get("owner"),
            "reviewer": fm.get("reviewer"),
            "source_ref": fm.get("source_ref"),
            "updated_at": str(fm.get("updated_at")),
            "file": os.path.relpath(p, ROOT).replace("\\", "/"),
        })
order = ["PROJECT","REQUIREMENT","BUSINESS_RULE","WORKFLOW","INTERFACE","TEST_SPEC","AUTOMATION","GLOSSARY","EXPERT_KNOWLEDGE","HISTORICAL_BUG"]
docs.sort(key=lambda d: (order.index(d["knowledge_type"]) if d["knowledge_type"] in order else 99, d["id"]))
out = {"questions": questions, "conflicts": conflicts, "gaps": gaps, "docs": docs,
       "counts": {"questions": len(questions), "conflicts": len(conflicts), "gaps": len(gaps), "docs": len(docs)}}
path = os.path.join(ROOT, "kb_content", "_delivery", "_build", "manual_items.json")
json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("written", path)
print(out["counts"])
print("blocking questions:", sum(1 for q in questions if q.get("blocking")))
print("open conflicts:", sum(1 for c in conflicts if c.get("status") == "open"))
print("docs types:", {t: sum(1 for d in docs if d["knowledge_type"] == t) for t in order})
