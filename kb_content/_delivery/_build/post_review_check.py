import os, re, yaml, json
from collections import Counter
KB = r"C:\Users\Viver\Desktop\综合电商测试平台demo\kb_content\minishop"
docs=[]
for dp,dns,fns in os.walk(KB):
    for fn in fns:
        if not fn.endswith(".md") or fn in ("README.md","release_notes.md"): continue
        p=os.path.join(dp,fn); t=open(p,encoding="utf-8").read()
        if not t.startswith("---"): continue
        parts=t.split("---",2)
        if len(parts)<3: continue
        fm=yaml.safe_load(parts[1])
        docs.append((fm.get("id"),fm.get("status"),fm.get("review_status"),fm.get("reviewer"),fm.get("reviewed_at"),fm.get("updated_at")))
print("docs",len(docs))
print("status",Counter(d[1] for d in docs))
print("review_status",Counter(d[2] for d in docs))
print("missing reviewer",[d[0] for d in docs if not d[3]])
print("missing reviewed_at",[d[0] for d in docs if not d[4]])
print("in_review list:",[d[0] for d in docs if d[1]=="in_review"])
# governance
for fn,key in (("_governance/pending_confirmation.yaml","items"),("_governance/conflicts.yaml","conflicts"),("_governance/knowledge_gaps.yaml","gaps")):
    d=yaml.safe_load(open(os.path.join(KB,fn),encoding="utf-8"))
    items=d[key]
    print(fn, len(items), Counter(x.get("status") for x in items))
    if key=="items": print("  answers missing:",[x["id"] for x in items if not x.get("decision")])
    if key=="gaps": print("  due missing:",[x["id"] for x in items if x.get("status")!="downgraded" and not x.get("due_date")])
