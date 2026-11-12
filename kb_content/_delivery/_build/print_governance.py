import yaml, os, json
p=r"kb_content\minishop\_governance\conflicts.yaml"; d=yaml.safe_load(open(p,encoding="utf-8"))
for c in d["conflicts"]:
    print(c["id"], c["status"], c.get("resolution_type"), "|", (c.get("resolution") or "")[:50])
print("--- gaps")
d=yaml.safe_load(open(r"kb_content\minishop\_governance\knowledge_gaps.yaml",encoding="utf-8"))
for g in d["gaps"]:
    print(g["id"], g["status"], g.get("status_cn"), g.get("due_date"), "|", (g.get("resolution_plan") or "")[:40])
print("--- pending")
d=yaml.safe_load(open(r"kb_content\minishop\_governance\pending_confirmation.yaml",encoding="utf-8"))
for q in d["items"]:
    print(q["id"], q["status"], q.get("decision"), q.get("decided_at"), "|", (q.get("decision_note") or "")[:40])
