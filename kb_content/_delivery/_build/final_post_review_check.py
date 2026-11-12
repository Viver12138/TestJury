import os, re, yaml, json
from collections import Counter
ROOT=r"C:\Users\Viver\Desktop\综合电商测试平台demo"
KB=os.path.join(ROOT,"kb_content","minishop")
docs=[]; records=0; bad=[]
for dp,dns,fns in os.walk(KB):
    for fn in fns:
        if not fn.endswith(".md") or fn in ("README.md","release_notes.md"): continue
        p=os.path.join(dp,fn); t=open(p,encoding="utf-8").read()
        if not t.startswith("---"): bad.append((fn,"no fm")); continue
        parts=t.split("---",2)
        if len(parts)<3: bad.append((fn,"bad fm")); continue
        fm=yaml.safe_load(parts[1]); body=parts[2]
        docs.append(fm)
        if body.count("## 复核记录（人工复核，2026-11-11）")==1: records+=1
        elif "## 复核记录" in body: bad.append((fn,"duplicate review record"))
        if fm.get("reviewed_at")!="2026-11-11": bad.append((fn,"reviewed_at"))
        if not fm.get("reviewer"): bad.append((fn,"reviewer"))
        if fm.get("updated_at")!="2026-11-12": bad.append((fn,"updated_at"))
print("docs",len(docs),"records",records,"bad",len(bad))
print("status",Counter(d.get("status") for d in docs))
print("review_status",Counter(d.get("review_status") for d in docs))
print("bad",bad[:10])
# validation result
v=json.load(open(os.path.join(ROOT,"kb_content","_delivery","validation_result.json"),encoding="utf-8"))
print("validation_result by_status",v["summary"]["by_status"],"errors",v["summary"]["errors"],"warnings",v["summary"]["warnings"])
