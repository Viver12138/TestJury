import os, re
ROOT=r"C:\Users\Viver\Desktop\综合电商测试平台demo"
KB=os.path.join(ROOT,"kb_content")
bad=[];checked=0
for dp,dns,fns in os.walk(KB):
    for fn in fns:
        if not fn.endswith(".md"): continue
        p=os.path.join(dp,fn); text=open(p,encoding="utf-8").read()
        for m in re.finditer(r"\]\(([^)]+)\)",text):
            t=m.group(1).split("#")[0].strip()
            if not t or t.startswith(("http://","https://","mailto:","#")): continue
            full=os.path.normpath(os.path.join(dp,t.replace("/",os.sep))); checked+=1
            if not os.path.exists(full): bad.append((os.path.relpath(p,ROOT),t))
print("links checked",checked,"broken",len(bad))
for b in bad: print(" -",b)
