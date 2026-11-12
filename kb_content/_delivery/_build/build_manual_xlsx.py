import json
import math
import os
import re
from datetime import date

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.properties import PageSetupProperties

ROOT = r"C:\Users\Viver\Desktop\综合电商测试平台demo"
DATA = json.load(open(os.path.join(ROOT, "kb_content", "_delivery", "_build", "manual_items.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "MiniShop_知识库人工确认清单.xlsx")

FONT = "微软雅黑"
DARK = "1F3864"
HEADER = "2F5597"
SUBTITLE = "D9E2F3"
INPUT = "FFF2CC"
BORDER = "BFBFBF"
RED = "FCE4E4"
GREEN = "E2EFDA"
AMBER = "FFF2CC"
BLUE = "DDEBF7"
GRAY = "EDEDED"

thin = Side(style="thin", color=BORDER)
BORDER_ALL = Border(left=thin, right=thin, top=thin, bottom=thin)
DARK_FILL = PatternFill("solid", start_color=DARK, end_color=DARK)
HEADER_FILL = PatternFill("solid", start_color=HEADER, end_color=HEADER)
SUBTITLE_FILL = PatternFill("solid", start_color=SUBTITLE, end_color=SUBTITLE)
INPUT_FILL = PatternFill("solid", start_color=INPUT, end_color=INPUT)
RED_FILL = PatternFill("solid", start_color=RED, end_color=RED)
GREEN_FILL = PatternFill("solid", start_color=GREEN, end_color=GREEN)
AMBER_FILL = PatternFill("solid", start_color=AMBER, end_color=AMBER)
BLUE_FILL = PatternFill("solid", start_color=BLUE, end_color=BLUE)
GRAY_FILL = PatternFill("solid", start_color=GRAY, end_color=GRAY)

TITLE_FONT = Font(name=FONT, size=16, bold=True, color="FFFFFF")
SUBTITLE_FONT = Font(name=FONT, size=10, color="404040")
HEADER_FONT = Font(name=FONT, size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name=FONT, size=10, color="262626")
NOTE_FONT = Font(name=FONT, size=9, color="595959")


def title_block(ws, title, subtitle, ncols):
    for c in range(1, ncols + 1):
        ws.cell(1, c).fill = DARK_FILL
        ws.cell(2, c).fill = SUBTITLE_FILL
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
    c = ws.cell(1, 1, title)
    c.font = TITLE_FONT
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    c2 = ws.cell(2, 1, subtitle)
    c2.font = SUBTITLE_FONT
    c2.alignment = Alignment(horizontal="left", vertical="center", indent=1, wrap_text=True)
    ws.row_dimensions[1].height = 38
    ws.row_dimensions[2].height = 30


def header_row(ws, headers, row=3):
    for i, h in enumerate(headers, 1):
        c = ws.cell(row, i, h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BORDER_ALL
    ws.row_dimensions[row].height = 40


def calc_height(values, widths):
    lines = 1
    for i, v in enumerate(values, 1):
        if v is None or v == "":
            continue
        text = str(v)
        col = get_column_letter(i)
        w = widths.get(col, 12)
        chars_per_line = max(6, int(w / 2.0))
        n = 0
        for seg in text.split("\n"):
            n += max(1, math.ceil(len(seg) / chars_per_line))
        lines = max(lines, n)
    return min(130, max(26, lines * 14 + 8))


def write_rows(ws, rows, widths, input_cols, start_row=4):
    for r, vals in enumerate(rows, start_row):
        for c, v in enumerate(vals, 1):
            cell = ws.cell(r, c, "" if v is None else v)
            cell.font = BODY_FONT
            cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            cell.border = BORDER_ALL
            if c in input_cols:
                cell.fill = INPUT_FILL
        ws.row_dimensions[r].height = calc_height(vals, widths)


def set_widths(ws, widths):
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def add_list_dv(ws, rng, values, title, prompt):
    dv = DataValidation(type="list", formula1='"' + ",".join(values) + '"', allow_blank=True)
    dv.showErrorMessage = True
    dv.errorTitle = "取值不合法"
    dv.error = "请从下拉列表选择：" + "、".join(values)
    dv.showInputMessage = True
    dv.promptTitle = title
    dv.prompt = prompt
    ws.add_data_validation(dv)
    dv.add(rng)


def add_date_dv(ws, rng):
    dv = DataValidation(type="date", operator="between", formula1="DATE(2026,1,1)", formula2="DATE(2030,12,31)", allow_blank=True)
    dv.showErrorMessage = True
    dv.errorTitle = "日期格式不正确"
    dv.error = "请填写 2026-01-01 至 2030-12-31 之间的日期"
    dv.showInputMessage = True
    dv.promptTitle = "确认日期"
    dv.prompt = "填写实际确认日期，例如 2026-11-20"
    ws.add_data_validation(dv)
    dv.add(rng)


def add_cf(ws, rng, formula, fill):
    ws.conditional_formatting.add(rng, FormulaRule(formula=[formula], fill=fill))


def s(v):
    return v.strip() if isinstance(v, str) else v


def clean_text(v):
    if not isinstance(v, str):
        return v
    t = re.sub(r"\s+", " ", v).strip()
    t = re.sub(r"\s+([，。；：！？、）】》])", r"\1", t)
    return t


def page_setup(ws, last_col, last_row):
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_title_rows = "1:3"
    ws.oddFooter.center.text = "第 &P 页 / 共 &N 页"
    ws.oddFooter.right.text = "MiniShop 知识库人工确认清单"


TYPE_LABEL = {
    "PROJECT": "项目级 (PROJECT)",
    "REQUIREMENT": "需求 (REQUIREMENT)",
    "BUSINESS_RULE": "业务规则 (BUSINESS_RULE)",
    "WORKFLOW": "流程/状态 (WORKFLOW)",
    "INTERFACE": "接口/数据 (INTERFACE)",
    "TEST_SPEC": "测试规范 (TEST_SPEC)",
    "AUTOMATION": "自动化 (AUTOMATION)",
    "GLOSSARY": "术语 (GLOSSARY)",
    "EXPERT_KNOWLEDGE": "专家经验 (EXPERT_KNOWLEDGE)",
    "HISTORICAL_BUG": "历史缺陷 (HISTORICAL_BUG)",
}

ROLE_LABEL = {
    "product_owner": "产品负责人",
    "tech_lead": "技术负责人",
    "test_lead": "测试负责人",
    "project_manager": "项目经理",
}

MODULE_LABEL = {
    None: "项目级",
    "order": "订单 (order)",
    "auth": "认证 (auth)",
    "catalog": "商品 (catalog)",
    "cart": "购物车 (cart)",
    "address": "地址 (address)",
    "coupon": "优惠券 (coupon)",
    "after_sales": "售后 (after_sales)",
    "review": "评价 (review)",
    "admin": "后台 (admin)",
}

CONFLICT_TYPE = {
    "doc_vs_implementation": "文档 vs 实现",
    "intent_vs_behavior": "意图 vs 行为",
    "documentation_drift": "文档漂移",
    "internal_inconsistency": "内部不一致",
    "deployment_inconsistency": "部署不一致",
    "field_semantics": "字段语义",
    "data_model_inconsistency": "数据模型不一致",
    "metric_definition": "指标口径",
    "state_transition_inconsistency": "状态转换不一致",
}

CONFLICT_PRIORITY = {
    "CONFLICT-001": "高",
    "CONFLICT-002": "高",
    "CONFLICT-003": "低",
    "CONFLICT-004": "高",
    "CONFLICT-005": "中",
    "CONFLICT-006": "高",
    "CONFLICT-007": "高",
    "CONFLICT-008": "中",
    "CONFLICT-009": "高",
    "CONFLICT-010": "高",
}

CONFLICT_BLOCKING = {"CONFLICT-001", "CONFLICT-002", "CONFLICT-004", "CONFLICT-006", "CONFLICT-007", "CONFLICT-009", "CONFLICT-010"}

CONFLICT_SUGGEST = {
    "CONFLICT-001": "以产品定义为准；若以当前实现为准，需更新 README 与 REQ-ORDER-001。",
    "CONFLICT-002": "明确是否引入库存预占；若不引入，在 README/RULE 中明确超卖限制与支付行为。",
    "CONFLICT-003": "更新 README 目录结构，删除不存在的 components/、router/、database/ 目录描述。",
    "CONFLICT-004": "确认 PENDING_SHIPMENT 是启用为“待发货”还是从代码与状态机中删除。",
    "CONFLICT-005": "补齐 backend/seed_media，或删除 Dockerfile 的 COPY 行与 Compose 挂载。",
    "CONFLICT-006": "明确 total_quantity 是发放量还是使用量，并统一领券、用券、可用券三处判断。",
    "CONFLICT-007": "明确订单详情展示最新/成功支付；必要时把 Order.payment 改为多对象或增加 current_payment_id。",
    "CONFLICT-008": "明确 Dashboard 销售额是否扣除退款，统一统计口径并在 README 说明。",
    "CONFLICT-009": "修复单规格商品默认选中 skus[0]；若产品不支持，需在 README 明确并调整 UI 用例。",
    "CONFLICT-010": "退款拒绝后恢复退款前状态（PAID/SHIPPED/COMPLETED），或在规则中明确统一回 PAID。",
}

GAP_ROLE = {
    "GAP-001": "产品负责人", "GAP-002": "产品负责人", "GAP-003": "测试负责人",
    "GAP-004": "测试负责人", "GAP-005": "测试负责人", "GAP-006": "技术负责人",
    "GAP-007": "技术负责人", "GAP-008": "产品负责人", "GAP-009": "技术负责人",
    "GAP-010": "产品负责人", "GAP-011": "产品负责人", "GAP-012": "产品负责人",
    "GAP-013": "产品负责人", "GAP-014": "技术负责人", "GAP-015": "项目经理",
}

Q_ACTION = {
    "Q-01": "更新 REQ-ORDER-001、FLOW-ORDER-001，关闭 CONFLICT-001",
    "Q-02": "更新 RULE-ORDER-003/009、STATE-ORDER-001，关闭 CONFLICT-002、GAP-012",
    "Q-03": "更新 RULE-ORDER-006；确认是否清空购物车",
    "Q-04": "更新 STATE-ORDER-001、RULE-ORDER-010，关闭 CONFLICT-010",
    "Q-05": "更新 RULE-ORDER-008、API-ORDER-003，关闭 CONFLICT-007",
    "Q-06": "更新 RULE-ORDER-004、DATA-ORDER-001，关闭 CONFLICT-006",
    "Q-07": "更新 RULE-ORDER-004，关闭 GAP-013",
    "Q-08": "更新 STATE-ORDER-001，关闭 CONFLICT-004",
    "Q-09": "更新 Dashboard 统计说明，关闭 CONFLICT-008",
    "Q-10": "修复前端或登记缺陷，关闭 CONFLICT-009",
    "Q-11": "更新 RULE-ORDER-010、API-ORDER-006",
    "Q-12": "更新 REQ-ORDER-004、STATE-ORDER-001，关闭 GAP-012",
    "Q-13": "修复 Docker 构建，关闭 CONFLICT-005、GAP-014",
    "Q-14": "修复 seed 图片生成逻辑，更新 AUTO-LIMITATIONS",
    "Q-15": "补 Git/发布记录，关闭 GAP-006、GAP-015",
}

RISK_CN = {"high": "高", "medium": "中", "low": "低", "open": "待处理"}
DOC_STATUS_CN = {"in_review": "in_review（待审核）", "approved": "approved（已批准）", "draft": "draft（草稿）"}


wb = Workbook()
wb.remove(wb.active)
wb.properties.title = "MiniShop 知识库人工确认清单"
wb.properties.subject = "TestJury 项目知识库候选稿人工审核"
wb.properties.creator = "TestJury KB Candidate Builder"
wb.properties.description = "基于 kb_content/minishop/_governance 与 37 份知识文档生成"

# ---------------- 1. 填写说明 ----------------
ws = wb.create_sheet("填写说明")
ws.sheet_view.showGridLines = False
ws.sheet_properties.tabColor = "7F7F7F"
set_widths(ws, {"A": 18, "B": 25, "C": 80})
for c in range(1, 4):
    ws.cell(1, c).fill = DARK_FILL
ws.merge_cells("A1:C1")
ws["A1"] = "MiniShop 知识库人工确认清单"
ws["A1"].font = TITLE_FONT
ws["A1"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
ws.row_dimensions[1].height = 40
ws.merge_cells("A2:C2")
ws["A2"] = "用于收集业务/技术/测试负责人对候选知识库中“需要人工判断”的事项。填写后请返回知识库维护者回写 YAML/Markdown。"
ws["A2"].font = SUBTITLE_FONT
ws["A2"].alignment = Alignment(horizontal="left", vertical="center", indent=1, wrap_text=True)
ws["A2"].fill = SUBTITLE_FILL
ws.row_dimensions[2].height = 34

info = [
    ("项目", "MiniShop 综合电商测试 Demo（项目标识 minishop）"),
    ("生成日期", "2026-11-11"),
    ("依据", "TestJury 项目知识库数据规范 v1.0"),
    ("数据来源", "kb_content/minishop/_governance/pending_confirmation.yaml、conflicts.yaml、knowledge_gaps.yaml；37 份知识文档"),
    ("事项数量", "77 条表格行：15 个待确认问题 + 10 个知识冲突 + 15 个知识缺口 + 37 份文档审核（存在交叉引用，不按唯一事项去重）"),
    ("当前状态", "37 份知识文档全部 in_review、reviewer=null；E1=0、approved=0，尚不能进入正式评审候选集"),
]
r = 4
for k, v in info:
    ws.cell(r, 1, k).font = Font(name=FONT, size=10, bold=True, color="262626")
    ws.cell(r, 1).fill = SUBTITLE_FILL
    ws.cell(r, 1).border = BORDER_ALL
    ws.cell(r, 1).alignment = Alignment(vertical="center", wrap_text=True)
    ws.cell(r, 2, v).font = BODY_FONT
    ws.cell(r, 2).alignment = Alignment(vertical="center", wrap_text=True)
    ws.cell(r, 2).border = BORDER_ALL
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    ws.row_dimensions[r].height = 30 if len(v) < 50 else 44
    r += 1

r += 1
ws.cell(r, 1, "填写顺序").font = Font(name=FONT, size=12, bold=True, color=DARK)
r += 1
steps = [
    ("第 1 步", "打开“待确认问题”，先回答 10 个 blocking=true 的问题。建议默认值仅用于讨论，不是结论。"),
    ("第 2 步", "打开“知识冲突”，对 10 个冲突给出裁决结论与处理状态；与 Q 编号重叠的冲突可引用 Q 的结论。"),
    ("第 3 步", "打开“知识缺口”，为 15 个缺口指定补充计划、负责人和完成日期。"),
    ("第 4 步", "打开“文档审核”，逐份审核 37 份文档；只有审核通过并填写审核人/日期后，才可把修改后状态改为 approved。"),
    ("第 5 步", "回到“处理总览”查看公式进度；把本文件返回知识库维护者，由维护者回写 YAML/Markdown 并更新 release_notes。"),
]
for k, v in steps:
    ws.cell(r, 1, k).font = Font(name=FONT, size=10, bold=True, color="1F3864")
    ws.cell(r, 1).border = BORDER_ALL
    ws.cell(r, 1).alignment = Alignment(vertical="center", wrap_text=True)
    ws.cell(r, 2, v).font = BODY_FONT
    ws.cell(r, 2).alignment = Alignment(vertical="top", wrap_text=True)
    ws.cell(r, 2).border = BORDER_ALL
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    ws.row_dimensions[r].height = 40
    r += 1

r += 1
ws.cell(r, 1, "颜色图例").font = Font(name=FONT, size=12, bold=True, color=DARK)
r += 1
legend = [
    ("浅黄色单元格", "需要你填写/选择", INPUT_FILL),
    ("浅红色单元格", "阻塞项、驳回或高风险", RED_FILL),
    ("浅绿色单元格", "已通过、已解决、已关闭", GREEN_FILL),
    ("浅橙色单元格", "待处理/待定，需要继续跟进", AMBER_FILL),
    ("浅蓝色单元格", "修改后通过、处理中", BLUE_FILL),
]
for k, v, fill in legend:
    c = ws.cell(r, 1, k)
    c.fill = fill
    c.border = BORDER_ALL
    c.font = Font(name=FONT, size=10, bold=True, color="262626")
    ws.cell(r, 2, v).font = BODY_FONT
    ws.cell(r, 2).alignment = Alignment(vertical="center", wrap_text=True)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    ws.row_dimensions[r].height = 24
    r += 1

r += 1
ws.cell(r, 1, "重要提醒").font = Font(name=FONT, size=12, bold=True, color="C00000")
r += 1
notes = [
    "本文件只收集人工判断，不自动修改知识库文件。",
    "不要在未审核的情况下把任何文档状态改为 approved；规范要求 approved 必须有 reviewer 和 reviewed_at。",
    "“建议默认值”是讨论起点，不是业务事实；不同意见请写在“结论说明/决策依据”。",
    "无法回答的问题请保留“待定”，并在备注中说明缺少什么资料，不要用行业惯例补齐。",
    "事项之间存在交叉引用（例如 Q-01 对应 CONFLICT-001），处理时请互相对照，避免同一问题得到两个相反结论。",
]
for v in notes:
    ws.cell(r, 1, "•").font = Font(name=FONT, size=10, color="C00000")
    ws.cell(r, 1).alignment = Alignment(horizontal="center", vertical="center")
    ws.cell(r, 2, v).font = BODY_FONT
    ws.cell(r, 2).alignment = Alignment(vertical="top", wrap_text=True)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    ws.row_dimensions[r].height = 32
    r += 1

# ---------------- 2. 处理总览 ----------------
ws = wb.create_sheet("处理总览")
ws.sheet_view.showGridLines = False
ws.sheet_properties.tabColor = "1F3864"
set_widths(ws, {"A": 24, "B": 12, "C": 22, "D": 14, "E": 10, "F": 62})
ws.column_dimensions["G"].width = 3
title_block(ws, "处理总览", "先看这里：各类人工事项的数量、阻塞/高风险项和填写进度。进度公式在 Excel 中打开后自动计算。", 6)
headers = ["类别", "事项数", "阻塞/高风险/待审核", "已处理（公式）", "进度", "说明"]
header_row(ws, headers)
ws.row_dimensions[3].height = 46
summary_rows = [
    ("待确认问题", len(DATA["questions"]), sum(1 for q in DATA["questions"] if q.get("blocking")),
     '=COUNTIF(\'待确认问题\'!$I$4:$I$18,"接受建议")+COUNTIF(\'待确认问题\'!$I$4:$I$18,"修改")+COUNTIF(\'待确认问题\'!$I$4:$I$18,"驳回")',
     "业务/技术决策；10 个阻塞问题优先"),
    ("知识冲突", len(DATA["conflicts"]), sum(1 for c in DATA["conflicts"] if c["id"] in CONFLICT_BLOCKING),
     '=COUNTIF(\'知识冲突\'!$L$4:$L$13,"已解决")+COUNTIF(\'知识冲突\'!$L$4:$L$13,"已降级")',
     "需裁决；部分与待确认问题重叠"),
    ("知识缺口", len(DATA["gaps"]), sum(1 for g in DATA["gaps"] if g.get("risk") == "high"),
     '=COUNTIF(\'知识缺口\'!$J$4:$J$18,"已关闭")+COUNTIF(\'知识缺口\'!$J$4:$J$18,"已降级")',
     "需补资料；高风险 7 项"),
    ("文档审核", len(DATA["docs"]), len(DATA["docs"]),
     '=COUNTIF(\'文档审核\'!$H$4:$H$40,"通过")+COUNTIF(\'文档审核\'!$H$4:$H$40,"修改后通过")',
     "逐份审核；通过后方可 approved"),
]
for i, (a, b, c, d, e) in enumerate(summary_rows, 5):
    vals = [a, b, c, d, f"=IF(B{i}=0,0,D{i}/B{i})", e]
    for j, v in enumerate(vals, 1):
        cell = ws.cell(i, j, v)
        cell.font = BODY_FONT
        cell.border = BORDER_ALL
        cell.alignment = Alignment(horizontal="center" if j in (2, 3, 4, 5) else "left", vertical="center", wrap_text=True)
        if j == 1:
            cell.font = Font(name=FONT, size=10, bold=True, color="1F3864")
            cell.fill = SUBTITLE_FILL
        if j == 5:
            cell.number_format = "0%"
    ws.row_dimensions[i].height = 34

note_r = 10
notes_summary = [
    "说明：事项存在交叉引用（例如 Q-01 对应 CONFLICT-001），不要用 77 行直接当作 77 个唯一决策。",
    "“已处理（公式）”只统计下拉值；如果打开时显示 0，按 F9 重算。",
    "文档审核通过后，仍需由知识库维护者在 Markdown 中填写 reviewer/reviewed_at 并把 status 改为 approved。",
]
for v in notes_summary:
    ws.cell(note_r, 1, v).font = NOTE_FONT
    ws.cell(note_r, 1).alignment = Alignment(vertical="top", wrap_text=True)
    ws.merge_cells(start_row=note_r, start_column=1, end_row=note_r, end_column=6)
    ws.row_dimensions[note_r].height = 28
    note_r += 1

chart = BarChart()
chart.type = "col"
chart.style = 10
chart.title = "各类人工事项数量"
chart.y_axis.title = "事项数"
chart.height = 7.5
chart.width = 13
data_ref = Reference(ws, min_col=2, min_row=4, max_row=8)
cats = Reference(ws, min_col=1, min_row=5, max_row=8)
chart.add_data(data_ref, titles_from_data=True)
chart.set_categories(cats)
chart.legend = None
chart.dataLabels = DataLabelList()
chart.dataLabels.showVal = True
chart.dataLabels.showSerName = False
chart.dataLabels.showCatName = False
chart.dataLabels.showLegendKey = False
chart.dataLabels.showPercent = False
chart.dataLabels.showBubbleSize = False
chart.dataLabels.position = "outEnd"
chart.series[0].graphicalProperties.solidFill = "2F5597"
ws.add_chart(chart, "H4")

# ---------------- 3. 待确认问题 ----------------
ws = wb.create_sheet("待确认问题")
ws.sheet_properties.tabColor = "C55A11"
widths = {"A": 10, "B": 22, "C": 58, "D": 28, "E": 34, "F": 14, "G": 16, "H": 12, "I": 14, "J": 38, "K": 12, "L": 12, "M": 30, "N": 24}
set_widths(ws, widths)
title_block(ws, "待确认问题（15 项）", "需要业务/技术/项目负责人给出结论。浅黄色列由你填写；建议默认值仅为讨论起点。", 14)
headers = ["编号", "主题", "需要确认的问题", "关联冲突/缺口", "建议默认值（仅供讨论）", "是否阻塞正式评审", "建议确认人角色", "当前状态", "人工结论", "结论说明 / 决策依据", "确认人", "确认日期", "后续动作", "备注"]
header_row(ws, headers)
ws.row_dimensions[3].height = 46
q_rows = []
for q in DATA["questions"]:
    q_rows.append([
        q["id"], clean_text(q["topic"]), clean_text(q["question"]),
        ", ".join(q.get("related_ids", [])),
        clean_text(q.get("suggested_default", "")),
        "是" if q.get("blocking") else "否",
        ROLE_LABEL.get(q.get("owner_role"), q.get("owner_role", "")),
        "待处理",
        "待定", "", "", "", clean_text(Q_ACTION.get(q["id"], "")), "",
    ])
write_rows(ws, q_rows, widths, {9, 10, 11, 12, 14}, 4)
ws.freeze_panes = "A4"
ws.auto_filter.ref = "A3:N18"
add_list_dv(ws, "F4:F18", ["是", "否"], "是否阻塞", "该问题不解决，是否阻塞正式评审？")
add_list_dv(ws, "H4:H18", ["待处理", "已处理"], "当前状态", "结论落地后改为“已处理”")
add_list_dv(ws, "I4:I18", ["接受建议", "修改", "驳回", "待定"], "人工结论", "接受建议/修改/驳回/待定")
add_date_dv(ws, "L4:L18")
add_cf(ws, "F4:F18", '$F4="是"', RED_FILL)
add_cf(ws, "H4:H18", '$H4="待处理"', AMBER_FILL)
add_cf(ws, "I4:I18", '$I4="驳回"', RED_FILL)
add_cf(ws, "I4:I18", 'OR($I4="接受建议",$I4="修改")', GREEN_FILL)
add_cf(ws, "I4:I18", '$I4="待定"', AMBER_FILL)
page_setup(ws, 14, 18)

# ---------------- 4. 知识冲突 ----------------
ws = wb.create_sheet("知识冲突")
ws.sheet_properties.tabColor = "C00000"
widths = {"A": 15, "B": 20, "C": 52, "D": 46, "E": 38, "F": 26, "G": 9, "H": 9, "I": 38, "J": 40, "K": 12, "L": 12, "M": 12, "N": 24}
set_widths(ws, widths)
title_block(ws, "知识冲突（10 项）", "冲突只登记、不裁决。请给出裁决结论与处理状态；与待确认问题重叠的，可直接引用 Q 编号的结论。", 14)
headers = ["冲突编号", "冲突类型", "冲突描述", "涉及来源", "影响范围", "关联知识", "优先级", "是否阻塞", "建议处理方向", "裁决结论", "负责人", "处理状态", "解决日期", "备注"]
header_row(ws, headers)
c_rows = []
for c in DATA["conflicts"]:
    c_rows.append([
        c["id"],
        CONFLICT_TYPE.get(c.get("type"), c.get("type", "")),
        clean_text(c.get("description", "")),
        "\n".join(s(x) for x in c.get("sources", [])),
        clean_text(c.get("impact", "")),
        ", ".join(c.get("related_knowledge_ids", [])),
        CONFLICT_PRIORITY.get(c["id"], "中"),
        "是" if c["id"] in CONFLICT_BLOCKING else "否",
        clean_text(CONFLICT_SUGGEST.get(c["id"], "")),
        "", "", "待处理", "", "",
    ])
write_rows(ws, c_rows, widths, set(range(10, 15)), 4)
ws.freeze_panes = "A4"
ws.auto_filter.ref = "A3:N13"
add_list_dv(ws, "G4:G13", ["高", "中", "低"], "优先级", "高/中/低")
add_list_dv(ws, "H4:H13", ["是", "否"], "是否阻塞", "是否阻塞正式评审？")
add_list_dv(ws, "L4:L13", ["待处理", "处理中", "已解决", "已降级"], "处理状态", "选择冲突处理状态")
add_date_dv(ws, "M4:M13")
add_cf(ws, "G4:G13", '$G4="高"', RED_FILL)
add_cf(ws, "G4:G13", '$G4="中"', AMBER_FILL)
add_cf(ws, "H4:H13", '$H4="是"', RED_FILL)
add_cf(ws, "L4:L13", '$L4="待处理"', AMBER_FILL)
add_cf(ws, "L4:L13", 'OR($L4="已解决",$L4="已降级")', GREEN_FILL)
add_cf(ws, "L4:L13", '$L4="处理中"', BLUE_FILL)
page_setup(ws, 14, 13)

# ---------------- 5. 知识缺口 ----------------
ws = wb.create_sheet("知识缺口")
ws.sheet_properties.tabColor = "BF8F00"
widths = {"A": 12, "B": 16, "C": 26, "D": 22, "E": 56, "F": 30, "G": 10, "H": 18, "I": 18, "J": 12, "K": 36, "L": 12, "M": 24}
set_widths(ws, widths)
title_block(ws, "知识缺口（15 项）", "缺口代表“当前没有可追溯资料”，不是业务规则不存在。请指定补充计划、负责人和完成日期。", 13)
headers = ["缺口编号", "模块", "主题", "缺失知识类型", "缺口说明", "影响评审维度", "风险等级", "建议补充人角色", "要求完成节点", "当前状态", "补充计划 / 负责人", "完成日期", "备注"]
header_row(ws, headers)
g_rows = []
for g in DATA["gaps"]:
    g_rows.append([
        g["id"],
        MODULE_LABEL.get(g.get("module_id"), g.get("module_id") or "项目级"),
        clean_text(g.get("topic", "")),
        g.get("missing_knowledge_type", ""),
        clean_text(g.get("description", "")),
        ", ".join(g.get("affected_review_dimensions", [])),
        RISK_CN.get(g.get("risk"), g.get("risk", "")),
        GAP_ROLE.get(g["id"], "项目负责人"),
        g.get("required_by", ""),
        "待处理", "", "", "",
    ])
write_rows(ws, g_rows, widths, set(range(10, 14)), 4)
ws.freeze_panes = "A4"
ws.auto_filter.ref = "A3:M18"
add_list_dv(ws, "G4:G18", ["高", "中", "低"], "风险等级", "高/中/低")
add_list_dv(ws, "J4:J18", ["待处理", "进行中", "已关闭", "已降级"], "缺口状态", "选择缺口处理状态")
add_date_dv(ws, "L4:L18")
add_cf(ws, "G4:G18", '$G4="高"', RED_FILL)
add_cf(ws, "G4:G18", '$G4="中"', AMBER_FILL)
add_cf(ws, "J4:J18", '$J4="待处理"', AMBER_FILL)
add_cf(ws, "J4:J18", 'OR($J4="已关闭",$J4="已降级")', GREEN_FILL)
add_cf(ws, "J4:J18", '$J4="进行中"', BLUE_FILL)
page_setup(ws, 13, 18)

# ---------------- 6. 文档审核 ----------------
ws = wb.create_sheet("文档审核")
ws.sheet_properties.tabColor = "548235"
widths = {"A": 20, "B": 34, "C": 28, "D": 12, "E": 10, "F": 20, "G": 55, "H": 14, "I": 12, "J": 12, "K": 38, "L": 14, "M": 20}
set_widths(ws, widths)
title_block(ws, "文档审核（37 份）", "逐份审核候选知识。审核通过并填写审核人/日期后，才可把“修改后状态”改为 approved；不要直接改“当前状态”。", 13)
headers = ["文档 ID", "标题", "知识类型", "模块", "证据等级", "当前状态", "来源定位", "审核结论", "审核人", "审核日期", "审核意见", "修改后状态", "备注"]
header_row(ws, headers)
d_rows = []
for d in DATA["docs"]:
    d_rows.append([
        d["id"], s(d["title"]),
        TYPE_LABEL.get(d["knowledge_type"], d["knowledge_type"]),
        MODULE_LABEL.get(d.get("module_id"), d.get("module_id") or "项目级"),
        d.get("evidence_level", ""),
        DOC_STATUS_CN.get(d.get("status"), d.get("status", "")),
        s(d.get("source_ref", "")),
        "待定", "", "", "", "", "",
    ])
write_rows(ws, d_rows, widths, set(range(8, 14)), 4)
ws.freeze_panes = "A4"
ws.auto_filter.ref = "A3:M40"
add_list_dv(ws, "H4:H40", ["通过", "修改后通过", "驳回", "待定"], "审核结论", "通过/修改后通过/驳回/待定")
add_date_dv(ws, "J4:J40")
add_list_dv(ws, "L4:L40", ["draft", "in_review", "approved", "rejected"], "修改后状态", "审核通过后选 approved；未通过选 in_review 或 rejected")
add_cf(ws, "F4:F40", '$F4="in_review（待审核）"', AMBER_FILL)
add_cf(ws, "H4:H40", '$H4="驳回"', RED_FILL)
add_cf(ws, "H4:H40", '$H4="通过"', GREEN_FILL)
add_cf(ws, "H4:H40", '$H4="修改后通过"', BLUE_FILL)
add_cf(ws, "H4:H40", '$H4="待定"', AMBER_FILL)
add_cf(ws, "L4:L40", '$L4="approved"', GREEN_FILL)
page_setup(ws, 13, 40)

# ---------------- 7. 字典 ----------------
ws = wb.create_sheet("字典")
ws.sheet_properties.tabColor = "7F7F7F"
ws.sheet_view.showGridLines = False
dict_headers = ["待确认结论", "冲突处理状态", "缺口状态", "文档审核结论", "文档状态", "风险/优先级", "角色", "是否"]
dict_values = [
    ["接受建议", "待处理", "待处理", "通过", "draft", "高", "产品负责人", "是"],
    ["修改", "处理中", "进行中", "修改后通过", "in_review", "中", "技术负责人", "否"],
    ["驳回", "已解决", "已关闭", "驳回", "approved", "低", "测试负责人", ""],
    ["待定", "已降级", "已降级", "待定", "rejected", "", "项目经理", ""],
    ["", "", "", "", "", "", "知识库维护者", ""],
]
for i, h in enumerate(dict_headers, 1):
    c = ws.cell(1, i, h)
    c.font = HEADER_FONT
    c.fill = HEADER_FILL
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    c.border = BORDER_ALL
    ws.column_dimensions[get_column_letter(i)].width = 20
ws.row_dimensions[1].height = 30
for r, row in enumerate(dict_values, 2):
    for c, v in enumerate(row, 1):
        cell = ws.cell(r, c, v)
        cell.font = BODY_FONT
        cell.border = BORDER_ALL
        cell.alignment = Alignment(horizontal="center", vertical="center")
ws.cell(8, 1, "说明：各表已使用内联下拉；本页用于查看允许值，不需要填写。").font = NOTE_FONT
ws.merge_cells("A8:H8")

# ---------------- save ----------------
wb.active = 0
wb.save(OUT)
print("saved", OUT)
print("sheets:", wb.sheetnames)
print("counts:", {"questions": len(DATA["questions"]), "conflicts": len(DATA["conflicts"]), "gaps": len(DATA["gaps"]), "docs": len(DATA["docs"])})
