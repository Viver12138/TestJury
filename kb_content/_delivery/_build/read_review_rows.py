import json
from openpyxl import load_workbook
p = r"C:\Users\Viver\Desktop\综合电商测试平台demo\MiniShop_知识库人工确认清单_复核修正版.xlsx"
wb = load_workbook(p, data_only=True)
def dump(name, first_row, last_row):
    ws = wb[name]
    headers = [ws.cell(3, c).value for c in range(1, ws.max_column + 1)]
    rows = []
    for r in range(first_row, last_row + 1):
        vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
        rows.append({headers[i] or f"col{i+1}": vals[i] for i in range(len(headers))})
    return rows
out = {"Q": dump("待确认问题",4,18), "C": dump("知识冲突",4,13), "G": dump("知识缺口",4,18), "D": dump("文档审核",4,40)}
json.dump(out, open(r"kb_content\_delivery\_build\review_input_rows.json","w",encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
print("written; Q/C/G/D rows:", len(out["Q"]), len(out["C"]), len(out["G"]), len(out["D"]))
