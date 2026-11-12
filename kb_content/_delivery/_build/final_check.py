from openpyxl import load_workbook
p = r"C:\Users\Viver\Desktop\综合电商测试平台demo\MiniShop_知识库人工确认清单.xlsx"
wb = load_workbook(p, data_only=False)
checks = []
def ok(name, cond, detail=""):
    checks.append((name, bool(cond), detail))
    if not cond:
        print("FAIL", name, detail)
ok("7 sheets", len(wb.sheetnames) == 7, str(wb.sheetnames))
ok("sheet names", wb.sheetnames == ["填写说明","处理总览","待确认问题","知识冲突","知识缺口","文档审核","字典"], str(wb.sheetnames))
q = wb["待确认问题"]; c = wb["知识冲突"]; g = wb["知识缺口"]; d = wb["文档审核"]; o = wb["处理总览"]; ins = wb["填写说明"]
ok("Q rows", q.max_row == 18 and q.max_column == 14, f"{q.max_row}x{q.max_column}")
ok("C rows", c.max_row == 13 and c.max_column == 14, f"{c.max_row}x{c.max_column}")
ok("G rows", g.max_row == 18 and g.max_column == 13, f"{g.max_row}x{g.max_column}")
ok("D rows", d.max_row == 40 and d.max_column == 13, f"{d.max_row}x{d.max_column}")
ok("Q first", q["A4"].value == "Q-01" and q["F4"].value == "是" and q["H4"].value == "待处理" and q["I4"].value == "待定", str([q.cell(4,i).value for i in (1,6,8,9)]))
ok("C first", c["A4"].value == "CONFLICT-001" and c["L4"].value == "待处理", str([c.cell(4,i).value for i in (1,12)]))
ok("G first", g["A4"].value == "GAP-001" and g["J4"].value == "待处理", str([g.cell(4,i).value for i in (1,10)]))
ok("D first", d["A4"].value is not None and d["H4"].value == "待定", str([d.cell(4,i).value for i in (1,8)]))
ok("instructions label", ins["A4"].value == "项目" and "MiniShop" in str(ins["B4"].value), str([ins["A4"].value, ins["B4"].value]))
ok("formula", str(o["D5"].value).startswith("=COUNTIF"), str(o["D5"].value)[:40])
ok("chart", len(o._charts) == 1)
ok("chart labels", o._charts[0].dataLabels.showVal is True and o._charts[0].dataLabels.showSerName is False)
ok("Q DV", len(q.data_validations.dataValidation) == 4, str(len(q.data_validations.dataValidation)))
ok("C DV", len(c.data_validations.dataValidation) == 4)
ok("G DV", len(g.data_validations.dataValidation) == 3)
ok("D DV", len(d.data_validations.dataValidation) == 3)
ok("freeze", q.freeze_panes == "A4" and d.freeze_panes == "A4")
ok("all Q rows", all(q.cell(r,1).value and q.cell(r,2).value and q.cell(r,3).value for r in range(4,19)))
ok("all C rows", all(c.cell(r,1).value and c.cell(r,2).value and c.cell(r,3).value for r in range(4,14)))
ok("all G rows", all(g.cell(r,1).value and g.cell(r,2).value and g.cell(r,3).value for r in range(4,19)))
ok("all D rows", all(d.cell(r,1).value and d.cell(r,2).value and d.cell(r,3).value for r in range(4,41)))
print("PASS", sum(1 for _,v,_ in checks if v), "/", len(checks))
print("wb bytes:", __import__("os").path.getsize(p))
