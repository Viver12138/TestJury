"""2026-11-12 独立审核：快照漂移检测 + 元数据复验。只读，不修改知识库。"""
import os, re, json, hashlib, datetime
import yaml

ROOT = r"C:\Users\Viver\Desktop\综合电商测试平台demo"
KB = os.path.join(ROOT, "kb_content", "minishop")
INV = os.path.join(ROOT, "kb_content", "_delivery", "source_inventory.yaml")

REQUIRED = ["id","title","knowledge_type","project_id","source_type","source_ref","source_version",
            "product_version","platforms","evidence_level","status","owner","reviewer",
            "created_at","updated_at","effective_from","effective_until","tags"]
KT = {"PROJECT","REQUIREMENT","BUSINESS_RULE","WORKFLOW","INTERFACE","TEST_SPEC","AUTOMATION","GLOSSARY","HISTORICAL_BUG","EXPERT_KNOWLEDGE"}
ST = {"PRD","REQUIREMENT_SPEC","DESIGN_DOC","API_SPEC","DATABASE_SCHEMA","TEST_STANDARD","AUTOMATION_DOC","BUG_TRACKER","MEETING_DECISION","EXPERT_REVIEW","OFFICIAL_WIKI","OTHER"}
EV = {"E1","E2","E3","E4"}
STAT = {"draft","in_review","approved","deprecated","superseded","rejected","archived"}

def is_date(v):
    if v is None: return True
    if isinstance(v, datetime.date): return True
    if not isinstance(v, str): return False
    try:
        datetime.date.fromisoformat(v); return True
    except Exception:
        return False

result = {"drift": [], "meta_errors": [], "meta_warnings": [], "counts": {}}

# ---- 1. drift: recompute sha256 of inventoried sources ----
inv = yaml.safe_load(open(INV, encoding="utf-8"))
checked = 0
for e in inv["sources"]:
    if not e.get("sha256"):
        continue
    p = os.path.join(ROOT, e["path"].replace("/", os.sep))
    if not os.path.exists(p):
        result["drift"].append({"path": e["path"], "issue": "file missing"})
        continue
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
    checked += 1
    if h != e["sha256"]:
        result["drift"].append({"path": e["path"], "issue": "sha256 changed", "old": e["sha256"][:12], "new": h[:12]})
result["counts"]["inventory_entries"] = len(inv["sources"])
result["counts"]["sha_checked"] = checked

# ---- 2. governance parse + ids ----
gov_ids = set()
gov_counts = {}
for rel, key in [("project/modules.yaml","modules"), ("_governance/knowledge_gaps.yaml","gaps"),
                 ("_governance/conflicts.yaml","conflicts"), ("_governance/pending_confirmation.yaml","items")]:
    d = yaml.safe_load(open(os.path.join(KB, rel), encoding="utf-8"))
    items = d.get(key, []) or []
    gov_counts[rel] = len(items)
    if d.get("id"): gov_ids.add(d["id"])
    for it in items:
        if isinstance(it, dict) and it.get("id"): gov_ids.add(it["id"])
result["counts"]["governance"] = gov_counts
result["counts"]["governance_ids"] = len(gov_ids)

# ---- 3. metadata validation over knowledge docs ----
docs, ids = [], {}
for dp, dns, fns in os.walk(KB):
    for fn in fns:
        if not fn.endswith(".md") or fn in ("README.md", "release_notes.md"):
            continue
        p = os.path.join(dp, fn)
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        text = open(p, encoding="utf-8").read()
        if not text.startswith("---"):
            result["meta_errors"].append((rel, "no front matter")); continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            result["meta_errors"].append((rel, "front matter not closed")); continue
        try:
            fm = yaml.safe_load(parts[1])
        except Exception as ex:
            result["meta_errors"].append((rel, "yaml parse: %s" % ex)); continue
        body = parts[2]
        docs.append((rel, fm, body))
        for f in REQUIRED:
            if f not in fm: result["meta_errors"].append((rel, "missing " + f))
        for f in ("product_version","platforms","tags"):
            if f in fm and not isinstance(fm[f], list): result["meta_errors"].append((rel, f + " not list"))
        if fm.get("knowledge_type") not in KT: result["meta_errors"].append((rel, "bad knowledge_type"))
        if fm.get("source_type") not in ST: result["meta_errors"].append((rel, "bad source_type"))
        if fm.get("evidence_level") not in EV: result["meta_errors"].append((rel, "bad evidence_level"))
        if fm.get("status") not in STAT: result["meta_errors"].append((rel, "bad status"))
        if fm.get("project_id") != "minishop": result["meta_errors"].append((rel, "bad project_id"))
        for f in ("created_at","updated_at","effective_from","effective_until","reviewed_at"):
            if f in fm and not is_date(fm[f]): result["meta_errors"].append((rel, "bad date " + f))
        if fm.get("status") == "approved" and (not fm.get("reviewer") or not fm.get("reviewed_at")):
            result["meta_errors"].append((rel, "approved without reviewer/reviewed_at"))
        if fm.get("status") == "in_review" and fm.get("reviewer") is not None and fm.get("review_status") != "changes_applied_pending_reapproval":
            result["meta_warnings"].append((rel, "in_review with reviewer set"))
        _id = fm.get("id")
        if _id:
            if _id in ids: result["meta_errors"].append((rel, "dup id " + _id))
            ids[_id] = rel

# ---- 4. source_ref existence + line range ----
anchors = 0
for rel, fm, body in docs:
    sref = fm.get("source_ref", "")
    if not isinstance(sref, str) or not sref.strip():
        result["meta_errors"].append((rel, "empty source_ref")); continue
    for part in [x.strip() for x in sref.split(";") if x.strip()]:
        p = part.split("#")[0].strip()
        if not p: continue
        if p.startswith("Minishop/") or p.startswith("kb_content/"):
            full = os.path.join(ROOT, p.replace("/", os.sep))
        elif os.path.isabs(p):
            full = p
        else:
            result["meta_warnings"].append((rel, "non-repo source_ref: " + p)); continue
        if not os.path.exists(full):
            result["meta_errors"].append((rel, "source missing: " + p)); continue
        m = re.search(r"#L(\d+)(?:-L(\d+))?", part)
        if m and os.path.isfile(full):
            a = int(m.group(1)); b = int(m.group(2) or m.group(1))
            n = sum(1 for _ in open(full, encoding="utf-8", errors="ignore"))
            anchors += 1
            if a < 1 or b > n or a > b:
                result["meta_errors"].append((rel, "line range out of bounds: %s (file %d lines)" % (part, n)))

# ---- 5. related_ids / module_id ----
mods = yaml.safe_load(open(os.path.join(KB, "project", "modules.yaml"), encoding="utf-8"))["modules"]
modids = {m["id"] for m in mods}
all_ids = set(ids) | gov_ids
for rel, fm, body in docs:
    for rid in fm.get("related_ids", []) or []:
        if rid not in all_ids: result["meta_errors"].append((rel, "unresolved related_id " + rid))
    mod = fm.get("module_id")
    if mod not in (None, "null") and mod not in modids:
        result["meta_errors"].append((rel, "module_id not in modules.yaml: %s" % mod))

# ---- 6. body duplicates ----
seen = {}
for rel, fm, body in docs:
    h = hashlib.sha256(body.encode()).hexdigest()
    if h in seen: result["meta_warnings"].append((rel, "duplicate body of " + seen[h]))
    seen[h] = rel

from collections import Counter
result["counts"]["docs"] = len(docs)
result["counts"]["ids"] = len(ids)
result["counts"]["anchors"] = anchors
result["counts"]["by_type"] = dict(Counter(f.get("knowledge_type") for _, f, _ in docs))
result["counts"]["by_status"] = dict(Counter(f.get("status") for _, f, _ in docs))
result["counts"]["by_evidence"] = dict(Counter(f.get("evidence_level") for _, f, _ in docs))
result["counts"]["errors"] = len(result["meta_errors"])
result["counts"]["warnings"] = len(result["meta_warnings"])
result["counts"]["drift"] = len(result["drift"])

out = os.path.join(ROOT, "kb_content", "_delivery", "_build", "audit_2026-11-12.json")
json.dump(result, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps(result["counts"], ensure_ascii=False, indent=2))
print("DRIFT:"); [print(" -", d) for d in result["drift"]]
print("META ERRORS:"); [print(" -", e) for e in result["meta_errors"]]
print("META WARNINGS:"); [print(" -", w) for w in result["meta_warnings"]]
print("written", out)

