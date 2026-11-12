import json, os
from openpyxl import load_workbook
p = r"C:\Users\Viver\Desktop\综合电商测试平台demo\MiniShop_知识库人工确认清单.xlsx"
wb = load_workbook(p, data_only=False)
out = {"sheets": wb.sheetnames, "props": {"title": wb.properties.title, "creator": wb.properties.creator}}
for ws in wb.worksheets:
    out[ws.title] = {
        "max_row": ws.max_row, "max_col": ws.max_column,
        "freeze": str(ws.freeze_panes),
        "dv": len(ws.data_validations.dataValidation),
        "cf": len(ws.conditional_formatting),
        "charts": len(ws._charts),
        "merged": [str(r) for r in ws.merged_cells.ranges][:8],
    }
# key cells
q = wb["待确认问题"]
c = wb["知识冲突"]
g = wb["知识缺口"]
d = wb["文档审核"]
o = wb["处理总览"]
out["samples"] = {
    "q_header": [q.cell(3, i).value for i in range(1, 15)],
    "q_first": [q.cell(4, i).value for i in range(1, 15)],
    "q_last": [q.cell(18, i).value for i in range(1, 15)],
    "c_first": [c.cell(4, i).value for i in range(1, 15)],
    "c_last": [c.cell(13, i).value for i in range(1, 15)],
    "g_first": [g.cell(4, i).value for i in range(1, 14)],
    "g_last": [g.cell(18, i).value for i in range(1, 14)],
    "d_first": [d.cell(4, i).value for i in range(1, 14)],
    "d_last": [d.cell(40, i).value for i in range(1, 14)],
    "overview_formulas": [o.cell(r, 4).value for r in range(5, 9)],
    "overview_progress": [o.cell(r, 5).value for r in range(5, 9)],
}
print(json.dumps(out, ensure_ascii=False, indent=2))
json.dump(out, open(r"kb_content\_delivery\_build\xlsx_check.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
