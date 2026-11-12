import json, os
from openpyxl import load_workbook
p = r"C:\Users\Viver\Desktop\综合电商测试平台demo\MiniShop_知识库人工确认清单_复核修正版.xlsx"
wb = load_workbook(p, data_only=True)
out = {"sheets": wb.sheetnames, "props": {"title": wb.properties.title, "creator": wb.properties.creator, "modified": str(wb.properties.modified)}}
for ws in wb.worksheets:
    rows = list(ws.iter_rows(values_only=True))
    nonempty = sum(1 for r in rows for v in r if v not in (None, ""))
    out[ws.title] = {"max_row": ws.max_row, "max_col": ws.max_column, "nonempty": nonempty,
                     "row1": [str(v) for v in rows[0][:12]] if rows else [],
                     "row3": [str(v) for v in rows[2][:16]] if len(rows) > 2 else []}
json.dump(out, open(r"kb_content\_delivery\_build\review_input_summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps({k: (v if k in ("sheets","props") else {kk: v[kk] for kk in ("max_row","max_col","nonempty")}) for k,v in out.items()}, ensure_ascii=False, indent=2))
