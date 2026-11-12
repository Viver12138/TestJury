import yaml, os
kb = r"kb_content\minishop\_governance"
for fn in ("pending_confirmation.yaml","conflicts.yaml","knowledge_gaps.yaml"):
    d = yaml.safe_load(open(os.path.join(kb,fn), encoding="utf-8"))
    print(fn, "OK", "top keys:", list(d.keys())[:5])
    items = d.get("items") or d.get("conflicts") or d.get("gaps")
    from collections import Counter
    key = "status"
    print("  items:", len(items), "status:", Counter(x.get(key) for x in items))
