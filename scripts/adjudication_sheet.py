"""人工裁决表（Excel，带下拉选项）的生成与回收。

CSV 没法带下拉框，所以人工裁决的主文件是 `adjudication.xlsx`：
- 一条候选一行，左侧直接带**原始用例全文**（前置条件/步骤/预期），不用再回翻 YAML；
- 需要人工填的字段改成下拉选择（裁决结论、严重级、问题分类、用例结论、缺陷数），
  裁决人可下拉也可手输；只有「改写建议 / 备注」这类自由文本保留手写；
- AI 的「建议/理由/建议严重级」放在裁决列右侧，避免先看答案再打标；
- 填完保存 xlsx，用 `to-csv` 回收成 `adjudication.csv`，再走原来的 `import-csv` 入库。

用法：
    python scripts/adjudication_sheet.py build           # 生成 xlsx，并刷新 adjudication.csv
    python scripts/adjudication_sheet.py build --force   # 已有裁决内容时也覆盖重建
    python scripts/adjudication_sheet.py check           # 只校验表内填写，不写文件
    python scripts/adjudication_sheet.py to-csv          # 把 xlsx 里的填写回收成 adjudication.csv
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from app.adjudication import (  # noqa: E402
    SEVERITY_VALUES,
    case_snapshot,
    export_csv,
    load_case,
)

DEFAULT_ROOT = ROOT / "data" / "adjudication"
WORKBOOK_NAME = "adjudication.xlsx"
CSV_NAME = "adjudication.csv"

VALIDITY_ORDER = ["valid", "invalid", "uncertain", "needs_spec"]
VERDICT_ORDER = ["in_progress", "pass", "needs_fix", "blocked", "uncertain"]
SEVERITY_ORDER = ["blocker", "major", "suggestion"]

# ---------------------------------------------------------------- 样式常量

NAVY = "1F3864"
BLUE = "305496"
AMBER = "7F6000"
READ_FILL = "F5F7FA"
WHITE = "FFFFFF"
SELECT_FILL = "FFF2CC"
LEVEL_FILL = "EAF1FB"
HINT_FILL = "F2F2F2"
GREY_LINE = "DDE2EA"
CASE_LINE = "8497B0"
CONFLICT_FILL = "FFC7CE"

FONT_NAME = "微软雅黑"


def fill(color: str):
    from openpyxl.styles import PatternFill

    return PatternFill(fill_type="solid", start_color=color, end_color=color)


def side(color: str = GREY_LINE, style: str = "thin"):
    from openpyxl.styles import Side

    return Side(style=style, color=color)


# ---------------------------------------------------------------- 列定义


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    width: float
    group: str
    kind: str  # read | select | text | hint | level
    hint: str = ""


COLUMNS: list[Column] = [
    Column("case_id", "用例编号\n(case_id)", 15, "case", "read"),
    Column("case_title", "用例标题\n(case_title)", 18.0, "case", "read"),
    Column("module", "所属模块\n(module)", 14.0, "case", "read"),
    Column("priority", "优先级\n(priority)", 12.0, "case", "read"),
    Column("source", "用例来源\n(source)", 24.0, "case", "read"),
    Column("ui_spec_ref", "规范引用\n(ui_spec_ref)", 15.0, "case", "read"),
    Column("preconditions", "前置条件\n(preconditions)", 24.0, "case", "read"),
    Column("steps", "测试步骤\n(steps)", 33.0, "case", "read"),
    Column("expected", "预期结果\n(expected)", 33.0, "case", "read"),
    Column("candidate_id", "候选编号\n(candidate_id)", 21.0, "candidate", "read"),
    Column("title", "AI 问题标题\n(title)", 26.0, "candidate", "read"),
    Column("claim", "AI 问题描述\n(claim)", 40.0, "candidate", "read"),
    Column("evidence_case", "证据·用例位置\n(evidence_case)", 17.0, "candidate", "read"),
    Column("evidence_spec", "证据·规范\n(evidence_spec)", 22.0, "candidate", "read"),
    Column("ai_recommendation", "AI 线索\n(ai_recommendation)", 18.0, "hint", "hint", hint="AI 的原始线索只是参考；建议先自己判，再看这一组。"),
    Column("ai_reason", "AI 理由\n(ai_reason)", 28.0, "hint", "hint"),
    Column("ai_suggested_severity", "AI 建议严重级\n(ai_suggested_severity)", 20.0, "hint", "hint"),
    Column("ai_suggested_validity", "AI 建议结论\n(ai_suggested_validity)", 20.0, "hint", "hint", hint="AI 建议的最终结论，不是人工标签；采纳与否由你决定。"),
    Column("ai_suggested_category", "AI 建议分类\n(ai_suggested_category)", 21.0, "hint", "hint"),
    Column("ai_suggested_correction", "AI 改写建议\n(ai_suggested_correction)", 38.0, "hint", "hint"),
    Column("ai_suggestion_note", "AI 建议说明\n(ai_suggestion_note)", 28.0, "hint", "hint"),
    Column("final_validity", "裁决结论\n(final_validity)", 18.0, "manual", "select", hint="必填。valid=问题成立需改用例；invalid=不成立；uncertain=信息不足；needs_spec=规范未定义需产品确认。"),
    Column("final_severity", "严重级\n(final_severity)", 18.0, "manual", "select", hint="仅 valid 填写：blocker / major / suggestion。invalid、uncertain、needs_spec 必须留空。"),
    Column("final_category", "问题分类\n(final_category)", 18.0, "manual", "select", hint="仅 valid 填写，从 Rubric 的 18 个分类里选一个。"),
    Column("correction", "改写建议\n(correction)", 34.0, "manual", "text", hint="valid 建议必填：写具体怎么改，不要写“建议补充”。"),
    Column("adjudicator", "裁决人\n(adjudicator)", 16.0, "manual", "text", hint="真实姓名/工号，不能写 AI、agent、system。"),
    Column("adjudicated_at", "裁决时间\n(adjudicated_at)", 20.0, "manual", "text", hint="可留空，导入时自动补当前时间（ISO 8601）。"),
    Column("note", "备注\n(note)", 24.0, "manual", "text", hint="裁决理由、合并关系、待确认事项。"),
    Column("ai_case_verdict", "AI 建议用例结论\n(ai_case_verdict)", 20.0, "level", "hint", hint="AI 静态建议，仅供对照；人工结论以 case_verdict 为准。"),
    Column("ai_case_defect_count", "AI 建议缺陷数\n(ai_case_defect_count)", 16.0, "level", "hint"),
    Column("ai_case_note", "AI 建议说明\n(ai_case_note)", 32.0, "level", "hint"),
    Column("case_verdict", "用例结论\n(case_verdict)", 16.0, "level", "select", hint="每个用例只在首行填一次：还有 pending 用 in_progress；最终结论要求该用例全部候选已裁决。"),
    Column("case_defect_count", "缺陷数\n(case_defect_count)", 21.0, "level", "select", hint="留空自动按 valid 条数计算；手填必须等于 valid 条数。"),
    Column("case_note", "用例备注\n(case_note)", 24.0, "level", "text", hint="拆分/重跑/待确认说明。"),
]

GROUP_TITLES = {
    "case": "① 原始案例（只读，来自 <case_id>.yaml）",
    "candidate": "② AI 候选问题（只读）",
    "hint": "③ AI 建议（只读，仅供参考；采不采纳由人决定）",
    "manual": "④ 人工裁决（黄色列下拉选择，白色列手写）",
    "level": "⑤ 用例级结论（先看 AI 建议，再填人工结论）",
}

COLUMN_INDEX = {column.key: index + 1 for index, column in enumerate(COLUMNS)}


def col_letter(key: str) -> str:
    from openpyxl.utils import get_column_letter

    return get_column_letter(COLUMN_INDEX[key])


CSV_ORDER = [
    "case_id",
    "case_title",
    "candidate_id",
    "title",
    "claim",
    "evidence_case",
    "evidence_spec",
    "ai_recommendation",
    "ai_reason",
    "ai_suggested_severity",
    "ai_suggested_validity",
    "ai_suggested_category",
    "ai_suggested_correction",
    "ai_suggestion_note",
    "module",
    "priority",
    "source",
    "ui_spec_ref",
    "preconditions",
    "steps",
    "expected",
    "final_validity",
    "final_severity",
    "final_category",
    "correction",
    "adjudicator",
    "adjudicated_at",
    "note",
    "case_verdict",
    "case_defect_count",
    "case_note",
    "ai_case_verdict",
    "ai_case_defect_count",
    "ai_case_note",
]


# ---------------------------------------------------------------- 选项来源


def rubric_vocabulary() -> tuple[list[str], list[str]]:
    """分类与严重级以 rubric 为准，避免脚本里再抄一份。"""

    categories: list[str] = []
    severities: list[str] = []
    path = ROOT / "rubric" / "rubric.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError:
        data = {}
    if isinstance(data.get("categories"), dict):
        categories = list(data["categories"].keys())
    if isinstance(data.get("severity"), dict):
        severities = [item for item in SEVERITY_ORDER if item in data["severity"]]
    if not categories:
        categories = [
            "覆盖缺失", "规则冲突", "意图不符", "前置不足", "术语不一致", "状态不自洽",
            "步骤不可执行", "预期不明确", "数据缺失", "边界缺失", "不可重复", "歧义",
            "自动化不可行", "状态不可读", "定位不稳定", "数据不可准备", "框架不匹配", "重复冗余",
        ]
    if not severities:
        severities = list(SEVERITY_ORDER)
    return categories, severities


def load_cases(root: Path) -> list[dict[str, Any]]:
    cases = [load_case(path) for path in sorted(Path(root).glob("*.yaml"))]
    if not cases:
        raise SystemExit(f"没有找到裁决 YAML：{root}")
    return cases


def case_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """展开成「一条候选一行」，并把原始用例快照贴到每一行。"""

    rows: list[dict[str, Any]] = []
    for case in cases:
        snapshot = case_snapshot(case)
        level = case.get("case_level", {}) or {}
        first = True
        for candidate in case.get("candidates", []):
            final = candidate.get("final", {}) or {}
            defect = level.get("defect_count")
            validity = final.get("validity") or "pending"
            verdict = level.get("verdict") or "pending"
            rows.append(
                {
                    "case_id": case.get("case_id"),
                    "case_title": case.get("case_title"),
                    **snapshot,
                    "candidate_id": candidate.get("candidate_id"),
                    "title": candidate.get("title"),
                    "claim": candidate.get("claim"),
                    "evidence_case": candidate.get("evidence_case"),
                    "evidence_spec": candidate.get("evidence_spec"),
                    "ai_recommendation": candidate.get("ai_recommendation"),
                    "ai_reason": candidate.get("ai_reason"),
                    "ai_suggested_severity": candidate.get("ai_suggested_severity"),
                    "ai_suggested_validity": candidate.get("ai_suggested_validity") or "",
                    "ai_suggested_category": candidate.get("ai_suggested_category") or "",
                    "ai_suggested_correction": candidate.get("ai_suggested_correction") or "",
                    "ai_suggestion_note": candidate.get("ai_suggestion_note") or "",
                    "final_validity": "" if validity == "pending" else validity,
                    "final_severity": final.get("severity") or "",
                    "final_category": final.get("category") or "",
                    "correction": final.get("correction") or "",
                    "adjudicator": final.get("adjudicator") or "",
                    "adjudicated_at": final.get("adjudicated_at") or "",
                    "note": final.get("note") or "",
                    "ai_case_verdict": (level.get("ai_suggested_verdict") or "") if first else "",
                    "ai_case_defect_count": (
                        level.get("ai_suggested_defect_count")
                        if level.get("ai_suggested_defect_count") is not None
                        else ""
                    ) if first else "",
                    "ai_case_note": (level.get("ai_suggested_note") or "") if first else "",
                    "case_verdict": ("" if verdict == "pending" else verdict) if first else "",
                    "case_defect_count": (defect if defect is not None else "") if first else "",
                    "case_note": (level.get("note") or "") if first else "",
                }
            )
            first = False
    return rows


# ---------------------------------------------------------------- 构建工作簿


def build_workbook(root: Path, destination: Path) -> dict[str, Any]:
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.worksheet.datavalidation import DataValidation  # noqa: F401

    categories, severities = rubric_vocabulary()
    cases = load_cases(root)
    rows = case_rows(cases)

    wb = Workbook()
    ws_intro = wb.active
    ws_intro.title = "填写说明"
    ws_main = wb.create_sheet("逐条裁决")
    ws_cases = wb.create_sheet("用例原文")
    ws_opt = wb.create_sheet("选项表")

    options = {
        "final_validity": VALIDITY_ORDER,
        "final_severity": severities,
        "final_category": categories,
        "case_verdict": VERDICT_ORDER,
        "case_defect_count": ["", "0", "1", "2", "3", "4", "5", "6"],
    }
    _build_options_sheet(ws_opt, options)

    data_start = 4
    data_end = data_start + len(rows) - 1
    validations = _build_validations(ws_opt, options)

    _build_main_sheet(ws_main, rows, cases, validations, data_start, data_end, Comment)
    _build_cases_sheet(ws_cases, cases)
    _build_intro_sheet(ws_intro, cases, len(rows))
    _add_conditional_formats(ws_main, data_start, data_end)

    wb.properties.title = "测试项目人工裁决表"
    wb.properties.creator = "评审团 adjudication workbench"
    wb.properties.description = "带下拉选项的人工裁决表；CSV 由 to-csv 命令回收。"
    ws_main.sheet_view.zoomScale = 85

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destination)
    return {"cases": len(cases), "candidates": len(rows), "path": str(destination)}


def _build_options_sheet(ws, options: dict[str, list[str]]) -> None:
    from openpyxl.styles import Alignment, Font

    ws.sheet_view.showGridLines = False
    headers = {
        "A": ("裁决结论 final_validity", options["final_validity"]),
        "B": ("严重级 final_severity", options["final_severity"]),
        "C": ("问题分类 final_category（Rubric 18 类）", options["final_category"]),
        "D": ("用例结论 case_verdict", options["case_verdict"]),
        "E": ("裁决人名单（填上姓名后，裁决人列即可下拉）", [""] * 20),
        "F": ("缺陷数 case_defect_count（空=自动计算）", options["case_defect_count"]),
    }
    for letter, (title, values) in headers.items():
        cell = ws[f"{letter}1"]
        cell.value = title
        cell.font = Font(name=FONT_NAME, bold=True, color=WHITE, size=9)
        cell.fill = fill(NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[letter].width = 34 if letter in {"C", "E"} else 22
        for index, value in enumerate(values, start=2):
            target = ws[f"{letter}{index}"]
            target.value = value or None
            target.font = Font(name=FONT_NAME, size=10)
    ws.row_dimensions[1].height = 42
    ws["E2"].comment = None

    meanings = [
        ("final_validity", "valid", "问题成立、用例必须改：影响执行或判定的都算"),
        ("final_validity", "invalid", "问题不成立：claim 与用例不符、规范未要求、纯风格偏好、重复问题"),
        ("final_validity", "uncertain", "信息不足无法判断（缺环境/缺数据），但不是规范未定义"),
        ("final_validity", "needs_spec", "规范/需求确实没写，需产品/设计确认，用例作者单方面改不了"),
        ("final_severity", "blocker", "无法执行、无法判定，或与权威依据直接冲突"),
        ("final_severity", "major", "明显降低有效性，执行者可凭经验补全"),
        ("final_severity", "suggestion", "可读性、规范性、优化类"),
        ("case_verdict", "in_progress", "该用例还有候选没裁决"),
        ("case_verdict", "pass", "0 条 valid，且没有 uncertain/needs_spec"),
        ("case_verdict", "needs_fix", "≥1 条 valid，但没有 valid blocker"),
        ("case_verdict", "blocked", "≥1 条 valid blocker"),
        ("case_verdict", "uncertain", "关键候选是 uncertain/needs_spec，给不了结论"),
    ]
    start_col = 8  # H
    for offset, title in enumerate(("字段", "取值", "含义 / 什么时候用")):
        cell = ws.cell(row=1, column=start_col + offset, value=title)
        cell.font = Font(name=FONT_NAME, bold=True, color=WHITE, size=9)
        cell.fill = fill(BLUE)
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.column_dimensions["H"].width = 18
    ws.column_dimensions["I"].width = 16
    ws.column_dimensions["J"].width = 62
    for index, (field, value, meaning) in enumerate(meanings, start=2):
        ws.cell(row=index, column=start_col, value=field).font = Font(name=FONT_NAME, size=10)
        ws.cell(row=index, column=start_col + 1, value=value).font = Font(name=FONT_NAME, size=10, bold=True)
        cell = ws.cell(row=index, column=start_col + 2, value=meaning)
        cell.font = Font(name=FONT_NAME, size=10)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(row=len(meanings) + 3, column=start_col, value="问题分类（18 类，仅 valid 填）").font = Font(
        name=FONT_NAME, bold=True, size=10
    )
    for offset, name in enumerate(options["final_category"]):
        ws.cell(row=len(meanings) + 4 + offset, column=start_col + 1, value=name).font = Font(name=FONT_NAME, size=10)
    ws.column_dimensions["A"].width = 26


def _build_validations(ws_opt, options: dict[str, list[str]]) -> dict[str, Any]:
    from openpyxl.worksheet.datavalidation import DataValidation

    def listed(col: str, last_row: int, *, prompt_title: str, prompt: str, strict: bool = True):
        dv = DataValidation(
            type="list",
            formula1=f"'{ws_opt.title}'!${col}$2:${col}${last_row}",
            allow_blank=True,
            showDropDown=False,
        )
        dv.showInputMessage = True
        dv.promptTitle = prompt_title
        dv.prompt = prompt
        if strict:
            dv.showErrorMessage = True
            dv.errorTitle = "请用下拉选择"
            dv.error = "该列只能从下拉列表中选择，请不要手输。"
            dv.errorStyle = "stop"
        else:
            dv.showErrorMessage = False
        return dv

    return {
        "final_validity": listed(
            "A",
            len(VALIDITY_ORDER) + 1,
            prompt_title="裁决结论",
            prompt="valid 成立 / invalid 不成立 / uncertain 信息不足 / needs_spec 规范未定义",
        ),
        "final_severity": listed(
            "B",
            len(options["final_severity"]) + 1,
            prompt_title="严重级",
            prompt="只有 valid 才填；其它结论必须留空。",
        ),
        "final_category": listed(
            "C",
            len(options["final_category"]) + 1,
            prompt_title="问题分类",
            prompt="只有 valid 才填，从 Rubric 18 类里选一个。",
        ),
        "case_verdict": listed(
            "D",
            len(VERDICT_ORDER) + 1,
            prompt_title="用例结论",
            prompt="每个用例只填首行；还有 pending 只能选 in_progress。",
        ),
        "case_defect_count": listed(
            "F",
            8,
            prompt_title="缺陷数",
            prompt="留空=导入时按 valid 条数自动算；手填必须等于 valid 条数。",
        ),
        "adjudicator": listed(
            "E",
            21,
            prompt_title="裁决人",
            prompt="可下拉选（先在「选项表」E 列填姓名），也可直接输入真实姓名/工号。",
            strict=False,
        ),
    }


def _visual_len(text: str) -> int:
    return sum(2 if ord(char) > 127 else 1 for char in text)


def _wrapped_lines(text: str, width: float) -> int:
    if not text:
        return 1
    usable = max(6.0, width - 1.5)
    total = 0
    for line in str(text).split("\n"):
        total += max(1, ceil(_visual_len(line) / usable))
    return total


def _row_height(row: dict[str, Any]) -> float:
    lines = 1
    for column in COLUMNS:
        if column.group in {"case", "candidate", "manual", "hint"}:
            lines = max(lines, _wrapped_lines(row.get(column.key) or "", column.width))
    return max(46.0, min(168.0, lines * 12.6 + 8))


def _build_main_sheet(ws, rows, cases, validations, data_start, data_end, Comment) -> None:
    from openpyxl.styles import Alignment, Border, Font
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.properties import PageSetupProperties

    ws.sheet_view.showGridLines = False
    last_col = get_column_letter(len(COLUMNS))

    ws.merge_cells(f"A1:{last_col}1")
    title = ws["A1"]
    title.value = (
        f"测试项目 · 人工裁决表（{len(cases)} 个用例 / {len(rows)} 条候选）"
        "　灰=只读原文　黄=下拉选择　白=手写　红=填写冲突　※ 先自己判，再看④ AI 提示"
    )
    title.font = Font(name=FONT_NAME, bold=True, size=13, color=WHITE)
    title.fill = fill(NAVY)
    title.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 28

    for group, text in GROUP_TITLES.items():
        span = [index + 1 for index, column in enumerate(COLUMNS) if column.group == group]
        first, last = span[0], span[-1]
        if last > first:
            ws.merge_cells(start_row=2, start_column=first, end_row=2, end_column=last)
        cell = ws.cell(row=2, column=first, value=text)
        cell.font = Font(name=FONT_NAME, bold=True, size=10, color=WHITE)
        cell.fill = fill(BLUE if group != "manual" else AMBER)
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 22

    for index, column in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=3, column=index, value=column.header)
        cell.font = Font(name=FONT_NAME, bold=True, size=9, color=WHITE)
        cell.fill = fill(NAVY if column.group in {"case", "candidate"} else (AMBER if column.group == "manual" else BLUE))
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if column.hint:
            comment = Comment(column.hint, "评审团")
            comment.width = 360
            comment.height = 150
            cell.comment = comment
        ws.column_dimensions[get_column_letter(index)].width = column.width
    ws.row_dimensions[3].height = 74

    previous_case = None
    band = 0
    for row_index in range(data_start, data_end + 1):
        row = rows[row_index - data_start]
        case_start = row["case_id"] != previous_case
        if case_start:
            band += 1
            previous_case = row["case_id"]
        banded = band % 2 == 0
        for col_index, column in enumerate(COLUMNS, start=1):
            value = row.get(column.key)
            cell = ws.cell(row=row_index, column=col_index)
            if value is None or value == "":
                cell.value = None
            elif column.key == "case_defect_count":
                try:
                    cell.value = int(value)
                except (TypeError, ValueError):
                    cell.value = str(value)
            else:
                cell.value = value
            cell.font = Font(name=FONT_NAME, size=9)
            cell.alignment = Alignment(
                wrap_text=True,
                vertical="top",
                horizontal="center" if column.kind == "select" else "left",
            )
            if column.group in {"case", "candidate"}:
                cell.fill = fill(READ_FILL if banded else WHITE)
            elif column.group == "manual":
                cell.fill = fill(SELECT_FILL if column.kind == "select" else WHITE)
            elif column.group == "hint":
                cell.fill = fill(HINT_FILL if banded else "FAFAFA")
            elif column.group == "level":
                cell.fill = fill(HINT_FILL if column.kind == "hint" else LEVEL_FILL)
            else:
                cell.fill = fill(LEVEL_FILL)
            top = side(CASE_LINE, "medium") if case_start else side()
            cell.border = Border(left=side(), right=side(), top=top, bottom=side())
        ws.row_dimensions[row_index].height = _row_height(row)

    ranges = {
        "final_validity": f"{col_letter('final_validity')}{data_start}:{col_letter('final_validity')}{data_end}",
        "final_severity": f"{col_letter('final_severity')}{data_start}:{col_letter('final_severity')}{data_end}",
        "final_category": f"{col_letter('final_category')}{data_start}:{col_letter('final_category')}{data_end}",
        "adjudicator": f"{col_letter('adjudicator')}{data_start}:{col_letter('adjudicator')}{data_end}",
        "case_verdict": f"{col_letter('case_verdict')}{data_start}:{col_letter('case_verdict')}{data_end}",
        "case_defect_count": f"{col_letter('case_defect_count')}{data_start}:{col_letter('case_defect_count')}{data_end}",
    }
    for key, ref in ranges.items():
        dv = validations[key]
        dv.add(ref)
        ws.add_data_validation(dv)

    at_col = COLUMN_INDEX["adjudicated_at"]
    for row_index in range(data_start, data_end + 1):
        ws.cell(row=row_index, column=at_col).number_format = "@"

    ws.freeze_panes = "D4"
    ws.auto_filter.ref = f"A3:{last_col}{data_end}"
    ws.print_title_rows = "1:3"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)


def _build_cases_sheet(ws, cases) -> None:
    from openpyxl.styles import Alignment, Border, Font
    from openpyxl.utils import get_column_letter

    ws.sheet_view.showGridLines = False
    ws.merge_cells("A1:K1")
    title = ws["A1"]
    title.value = "原始用例原文（与 <case_id>.yaml 的用例快照一致；只读）"
    title.font = Font(name=FONT_NAME, bold=True, size=12, color=WHITE)
    title.fill = fill(NAVY)
    title.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 26

    headers = [
        ("用例编号", 15),
        ("用例标题", 22),
        ("所属模块", 16),
        ("优先级", 9),
        ("用例来源", 24),
        ("规范引用", 13),
        ("前置条件", 34),
        ("测试步骤", 46),
        ("预期结果", 46),
        ("候选数", 8),
        ("用例结论", 13),
    ]
    for index, (text, width) in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=index, value=text)
        cell.font = Font(name=FONT_NAME, bold=True, size=10, color=WHITE)
        cell.fill = fill(BLUE)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.row_dimensions[2].height = 24

    for offset, case in enumerate(cases):
        row_index = 3 + offset
        snapshot = case_snapshot(case)
        level = case.get("case_level", {}) or {}
        values = [
            case.get("case_id"),
            case.get("case_title"),
            snapshot["module"],
            snapshot["priority"],
            snapshot["source"],
            snapshot["ui_spec_ref"],
            snapshot["preconditions"],
            snapshot["steps"],
            snapshot["expected"],
            len(case.get("candidates", [])),
            level.get("verdict") or "pending",
        ]
        for col_index, value in enumerate(values, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            cell.font = Font(name=FONT_NAME, size=10)
            cell.alignment = Alignment(
                wrap_text=True,
                vertical="top",
                horizontal="center" if col_index in {4, 10, 11} else "left",
            )
            cell.border = Border(left=side(), right=side(), top=side(), bottom=side())
            cell.fill = fill(READ_FILL if offset % 2 else WHITE)
        lines = max(
            _wrapped_lines(snapshot["preconditions"], 34),
            _wrapped_lines(snapshot["steps"], 46),
            _wrapped_lines(snapshot["expected"], 46),
        )
        ws.row_dimensions[row_index].height = max(50.0, min(150.0, lines * 13.5 + 10))
    ws.freeze_panes = "B3"


def _build_intro_sheet(ws, cases, total_candidates) -> None:
    from openpyxl.styles import Alignment, Font

    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 108

    def banner(text: str, row: int, *, size: int, color: str) -> int:
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        cell = ws.cell(row=row, column=2, value=text)
        cell.font = Font(name=FONT_NAME, bold=True, size=size, color=WHITE)
        cell.fill = fill(color)
        cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[row].height = 30 if size >= 13 else 24
        return row + 1

    def line(label: str, text: str, row: int) -> int:
        label_cell = ws.cell(row=row, column=2, value=label)
        label_cell.font = Font(name=FONT_NAME, size=10, bold=True)
        label_cell.alignment = Alignment(vertical="top", wrap_text=True)
        value_cell = ws.cell(row=row, column=3, value=text)
        value_cell.font = Font(name=FONT_NAME, size=10)
        value_cell.alignment = Alignment(vertical="top", wrap_text=True)
        ws.row_dimensions[row].height = max(18, 15 * ceil(_visual_len(text) / 104) + 4)
        return row + 1

    row = 2
    row = banner("人工裁决表 · 使用说明", row, size=14, color=NAVY)
    row = line(
        "批次",
        f"测试项目用例 · {len(cases)} 个用例 / {total_candidates} 条候选 · 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        row,
    )
    row = line("数据源", "adjudication/<case_id>.yaml（唯一事实源）。本表只负责填写，不直接改 YAML；填完用 to-csv + import-csv 入库。", row)
    row = line("怎么读", "表格从 ①→⑤ 排：①原始案例 → ②AI 指出的问题 → ③你来判 → ④AI 的参考答案 → ⑤用例级结论。先判再看④，避免被 AI 锚定。", row)

    row += 1
    row = banner("一、三步流程", row, size=11, color=BLUE)
    row = line("1 读原文", "「逐条裁决」每行左侧①就是该用例的完整原文（前置条件、测试步骤、预期结果），不用再翻 YAML。", row)
    row = line("2 选结论", "看②的 claim 是否成立，在③黄色列下拉选「裁决结论」；判 valid 时再选「严重级」「问题分类」。", row)
    row = line("3 写改写", "「改写建议」「备注」「裁决人」手写；保存 xlsx，然后在仓库执行第二节的命令。", row)

    row += 1
    row = banner("二、提交命令（在仓库根目录执行）", row, size=11, color=BLUE)
    row = line("回收", r"python scripts\adjudication_sheet.py to-csv", row)
    row = line("预检", r"python scripts\adjudicate.py import-csv --dry-run", row)
    row = line("入库", r"python scripts\adjudicate.py import-csv", row)
    row = line("进度", r"python scripts\adjudicate.py stats", row)
    row = line("重建表", r"python scripts\adjudication_sheet.py build   （已有裁决内容时会拒绝覆盖，确认丢弃才加 --force）", row)

    row += 1
    row = banner("三、每个下拉字段怎么选", row, size=11, color=BLUE)
    row = line("裁决结论", "valid 问题成立、用例要改（影响执行或判定）｜invalid 问题不成立｜uncertain 信息不足（缺环境/数据）｜needs_spec 规范没写、需产品确认", row)
    row = line("严重级", "blocker 无法执行/无法判定/与权威依据冲突｜major 明显降低有效性｜suggestion 可读性优化；只有 valid 才填", row)
    row = line("问题分类", "Rubric 18 类，例如：预期不明确、不可重复、步骤不可执行、状态不可读、前置不足、重复冗余；只有 valid 才填", row)
    row = line("用例结论", "in_progress 还有候选没裁决｜pass 0 条 valid｜needs_fix ≥1 valid 无 blocker｜blocked 有 valid blocker｜uncertain 关键项定不了", row)
    row = line("缺陷数", "留空＝导入时按 valid 条数自动算；手填必须正好等于 valid 条数", row)

    row += 1
    row = banner("四、导入会校验的硬规则", row, size=11, color=BLUE)
    row = line("规则 1", "valid 必须同时有严重级 + 问题分类，否则导入直接失败。", row)
    row = line("规则 2", "invalid / uncertain / needs_spec 的「严重级」必须留空，填了会被拒绝。", row)
    row = line("规则 3", "裁决人必须是真实姓名/工号，不能写 AI、agent、system；整行为空的行会被跳过。", row)
    row = line("规则 4", "用例结论填最终结论（pass/needs_fix/blocked/uncertain）时，该用例所有候选必须已裁决；还有 pending 只能填 in_progress。", row)
    row = line("规则 5", "pass 不允许存在 valid；needs_fix 至少 1 条 valid；blocked 至少 1 条 valid blocker。", row)
    row = line("规则 6", "用例结论/缺陷数/用例备注每个用例只在首行填一次，同用例其它行留空。", row)

    row += 1
    row = banner("五、颜色图例", row, size=11, color=BLUE)
    row = line("只读", "灰色列 = 用例原文与 AI 候选，不要改；改了会导致 claim 与证据对不上。", row)
    row = line("可填", "黄色 = 下拉选择；白色 = 手写文本；浅蓝 = 用例级结论。", row)
    row = line("结论配色", "浅绿 valid｜浅灰 invalid｜浅橙 needs_spec｜浅蓝 uncertain｜浅黄 待裁决。", row)
    row = line("红底告警", "红底 = 填写冲突（例如非 valid 却填了严重级、valid 没填严重级/分类）。", row)

    row += 1
    row = banner("六、不要做", row, size=11, color=BLUE)
    row = line("不要", "增删行、改列名（导入按列名匹配）、合并单元格、修改用例编号/候选编号；新增候选请改 YAML 后重新 build。", row)
    row = line("不要", "同时改 xlsx 和 adjudication.csv：只改一份。xlsx 是填写入口，csv 是回收产物。", row)
    row = line("不要", "照抄 AI 建议：ai_recommendation 只是线索，likely_valid ≠ valid。", row)


def _add_conditional_formats(ws, data_start: int, data_end: int) -> None:
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import Font

    validity_col = col_letter("final_validity")
    severity_col = col_letter("final_severity")
    category_col = col_letter("final_category")

    rules = [
        (f'${validity_col}4="valid"', "C6EFCE", "375623"),
        (f'${validity_col}4="invalid"', "EDEDED", "595959"),
        (f'${validity_col}4="needs_spec"', "FCE4D6", "833C0B"),
        (f'${validity_col}4="uncertain"', "DDEBF7", "1F4E79"),
        (f'OR(${validity_col}4="",${validity_col}4="pending")', "FFF2CC", "7F6000"),
    ]
    for formula, bg, fg in rules:
        ws.conditional_formatting.add(
            f"{validity_col}{data_start}:{validity_col}{data_end}",
            FormulaRule(formula=[formula], fill=fill(bg), font=Font(color=fg), stopIfTrue=True),
        )

    ws.conditional_formatting.add(
        f"{severity_col}{data_start}:{severity_col}{data_end}",
        FormulaRule(
            formula=[f'AND(${validity_col}4<>"valid",${validity_col}4<>"",${validity_col}4<>"pending",${severity_col}4<>"")'],
            fill=fill(CONFLICT_FILL),
            font=Font(color="9C0006", bold=True),
            stopIfTrue=True,
        ),
    )
    ws.conditional_formatting.add(
        f"{severity_col}{data_start}:{severity_col}{data_end}",
        FormulaRule(formula=[f'AND(${validity_col}4="valid",${severity_col}4="")'], fill=fill(CONFLICT_FILL), stopIfTrue=True),
    )
    ws.conditional_formatting.add(
        f"{category_col}{data_start}:{category_col}{data_end}",
        FormulaRule(formula=[f'AND(${validity_col}4="valid",${category_col}4="")'], fill=fill(CONFLICT_FILL), stopIfTrue=True),
    )


# ---------------------------------------------------------------- 回收 CSV


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_workbook(path: Path) -> list[dict[str, str]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("需要 openpyxl：python -m pip install openpyxl") from exc

    wb = load_workbook(path, data_only=True)
    if "逐条裁决" not in wb.sheetnames:
        raise SystemExit(f"工作簿缺少「逐条裁决」工作表：{path}")
    ws = wb["逐条裁决"]

    header_map: dict[int, str] = {}
    for col_index in range(1, ws.max_column + 1):
        raw = ws.cell(row=3, column=col_index).value
        if not raw:
            continue
        header = str(raw).strip()
        for column in COLUMNS:
            if header == column.header:
                header_map[col_index] = column.key
                break
    missing = [c.header for c in COLUMNS if c.key not in header_map.values()]
    if missing:
        raise SystemExit("表头不完整，无法回收。缺少列：" + "；".join(h.replace("\n", " ") for h in missing))

    records: list[dict[str, str]] = []
    for row_index in range(4, ws.max_row + 1):
        record: dict[str, str] = {}
        filled = False
        for col_index, key in header_map.items():
            text = _cell_text(ws.cell(row=row_index, column=col_index).value)
            record[key] = text
            if text:
                filled = True
        if not filled:
            continue
        record["_row"] = str(row_index)
        records.append(record)
    return records


def write_csv(records: list[dict[str, str]], destination: Path) -> int:
    import csv

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    # 用例级字段只在首行填；导出时按用例补齐，保证 CSV 与 export-csv 的形状一致
    case_level: dict[str, dict[str, str]] = {}
    for record in records:
        case_id = record.get("case_id", "")
        bucket = case_level.setdefault(case_id, {})
        for key in ("case_verdict", "case_defect_count", "case_note"):
            if not bucket.get(key) and record.get(key):
                bucket[key] = record[key]

    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_ORDER, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = {key: record.get(key, "") for key in CSV_ORDER}
            if not row["final_validity"]:
                row["final_validity"] = "pending"
            bucket = case_level.get(record.get("case_id", ""), {})
            for key in ("case_verdict", "case_defect_count", "case_note"):
                if not row[key] and bucket.get(key):
                    row[key] = bucket[key]
            if not row["case_verdict"]:
                row["case_verdict"] = "pending"
            writer.writerow(row)
    return len(records)


def check_records(records: list[dict[str, str]]) -> list[str]:
    problems: list[str] = []
    for record in records:
        row = record.get("_row", "?")
        validity = record.get("final_validity", "").strip()
        severity = record.get("final_severity", "").strip()
        category = record.get("final_category", "").strip()
        adjudicator = record.get("adjudicator", "").strip()
        label = f"第 {row} 行 {record.get('case_id', '')}/{record.get('candidate_id', '')}"
        if not validity or validity == "pending":
            continue
        if validity not in VALIDITY_ORDER:
            problems.append(f"{label}：裁决结论 {validity!r} 不在允许值内")
        if validity == "valid":
            if not severity:
                problems.append(f"{label}：valid 缺严重级")
            elif severity not in SEVERITY_VALUES:
                problems.append(f"{label}：严重级 {severity!r} 不在允许值内")
            if not category:
                problems.append(f"{label}：valid 缺问题分类")
        elif severity:
            problems.append(f"{label}：{validity} 不应填写严重级（{severity}）")
        if not adjudicator:
            problems.append(f"{label}：缺裁决人")
        elif adjudicator.lower() in {"ai", "agent", "system", "bot"}:
            problems.append(f"{label}：裁决人不能是 {adjudicator!r}")
    return problems


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="人工裁决表（带下拉选项）构建与回收")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="adjudication 目录")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="生成 adjudication.xlsx 并刷新 adjudication.csv")
    build.add_argument("--force", action="store_true", help="已有裁决内容时也覆盖重建")
    build.add_argument("--out", help="xlsx 输出路径")

    to_csv = sub.add_parser("to-csv", help="把 xlsx 的填写回收成 adjudication.csv")
    to_csv.add_argument("--xlsx", help="xlsx 路径（默认 <root>/adjudication.xlsx）")
    to_csv.add_argument("--out", help="csv 输出路径（默认 <root>/adjudication.csv）")

    check = sub.add_parser("check", help="只校验表内填写，不写文件")
    check.add_argument("--xlsx", help="xlsx 路径（默认 <root>/adjudication.xlsx）")

    args = parser.parse_args(argv)
    root = Path(args.root)

    if args.command == "build":
        workbook = Path(args.out) if args.out else root / WORKBOOK_NAME
        if workbook.exists() and not args.force:
            try:
                existing = read_workbook(workbook)
            except SystemExit:
                existing = []
            decided = [
                record
                for record in existing
                if (record.get("final_validity") or "").strip() not in {"", "pending"}
            ]
            if decided:
                print(f"已有 {len(decided)} 条裁决写在 {workbook.name}，已停止以免覆盖。")
                print("确认丢弃这些填写后重跑：python scripts/adjudication_sheet.py build --force")
                return 1
        result = build_workbook(root, workbook)
        count = export_csv(root, root / CSV_NAME)
        print(f"已生成 {result['path']}")
        print(f"用例 {result['cases']} 个 / 候选 {result['candidates']} 条；同步刷新 {root / CSV_NAME}（{count} 行）")
        return 0

    if args.command == "to-csv":
        workbook = Path(args.xlsx) if args.xlsx else root / WORKBOOK_NAME
        destination = Path(args.out) if args.out else root / CSV_NAME
        if not workbook.exists():
            print(f"[ERROR] 找不到工作簿：{workbook}")
            return 1
        records = read_workbook(workbook)
        problems = check_records(records)
        if problems:
            print("填写校验未通过，未写 CSV：")
            for item in problems:
                print("  - " + item)
            return 1
        count = write_csv(records, destination)
        print(f"已从 {workbook.name} 回收 {count} 行到 {destination}")
        print("下一步：python scripts/adjudicate.py import-csv --dry-run")
        return 0

    if args.command == "check":
        workbook = Path(args.xlsx) if args.xlsx else root / WORKBOOK_NAME
        if not workbook.exists():
            print(f"[ERROR] 找不到工作簿：{workbook}")
            return 1
        records = read_workbook(workbook)
        problems = check_records(records)
        decided = sum(1 for record in records if (record.get("final_validity") or "").strip() not in {"", "pending"})
        print(f"共 {len(records)} 条候选，已裁决 {decided} 条，待裁决 {len(records) - decided} 条")
        if not problems:
            print("校验通过，可以执行 to-csv + import-csv。")
            return 0
        print(f"发现 {len(problems)} 个问题：")
        for item in problems:
            print("  - " + item)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
