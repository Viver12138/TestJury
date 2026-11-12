import os, yaml
from collections import Counter
KB=r"C:\Users\Viver\Desktop\综合电商测试平台demo\kb_content\minishop"
docs=[]
for dp,dns,fns in os.walk(KB):
    for fn in fns:
        if not fn.endswith(".md") or fn in ("README.md","release_notes.md"): continue
        t=open(os.path.join(dp,fn),encoding="utf-8").read()
        parts=t.split("---",2)
        if len(parts)<3: continue
        docs.append(yaml.safe_load(parts[1]))
bad=[d["id"] for d in docs if str(d.get("reviewed_at"))!="2026-11-11" or str(d.get("updated_at"))!="2026-11-12" or not d.get("reviewer")]
print("docs",len(docs),"bad",len(bad),bad)
print(Counter(d["status"] for d in docs))
