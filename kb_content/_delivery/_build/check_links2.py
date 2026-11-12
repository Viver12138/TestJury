import os,re
ROOT=r"C:\Users\Viver\Desktop\综合电商测试平台demo"; KB=os.path.join(ROOT,"kb_content")
bad=[];n=0
for dp,dns,fns in os.walk(KB):
    for fn in fns:
        if not fn.endswith(".md"): continue
        p=os.path.join(dp,fn); t=open(p,encoding="utf-8").read()
        for m in re.finditer(r"\]\(([^)]+)\)",t):
            x=m.group(1).split("#")[0].strip()
            if not x or x.startswith(("http://","https://","mailto:","#")): continue
            full=os.path.normpath(os.path.join(dp,x.replace("/",os.sep))); n+=1
            if not os.path.exists(full): bad.append((os.path.relpath(p,ROOT),x))
print("links",n,"broken",len(bad)); [print(" -",b) for b in bad]
