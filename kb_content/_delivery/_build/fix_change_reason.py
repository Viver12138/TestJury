import os, re
KB = r"C:\Users\Viver\Desktop\综合电商测试平台demo\kb_content\minishop"
n = 0
for dp, dns, fns in os.walk(KB):
    for fn in fns:
        if not fn.endswith(".md") or fn in ("README.md", "release_notes.md"):
            continue
        p = os.path.join(dp, fn)
        text = open(p, encoding="utf-8").read()
        new = re.sub(r'^change_reason: \\"(.*)\\"$', r'change_reason: "\1"', text, count=1, flags=re.M)
        if new != text:
            open(p, "w", encoding="utf-8").write(new)
            n += 1
print("fixed change_reason in", n, "docs")
