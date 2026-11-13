"""Readable Excel exports of stored reports; never rerun or mutate a review."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta, timezone
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.storage.models import ReviewJob

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
STATUSES = {"queued": "等待评审", "processing": "正在评审", "retrying": "正在重试", "done": "评审完成",
            "completed_with_warnings": "评审完成（有待复核事项）", "failed": "评审失败", "cancelled": "已取消"}
VERDICTS = {"blocked": "存在阻断问题", "conditional": "未形成阻断结论（需结合问题复核）", "need_human": "需要复核"}
HUMAN = {"pending": "待人工审批", "approved": "人工已批准", "rejected": "人工已拒绝", "changes_requested": "要求修改"}
SEVERITY = {"blocker": "阻断", "major": "重要", "suggestion": "建议"}
ISSUE_STATUS = {"adopted": "采纳", "rejected": "不采纳", "disputed": "有分歧", "need_human": "待复核"}
INVALID_XML = re.compile(r"[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return INVALID_XML.sub(lambda m: f"\\u{ord(m[0]):04x}", str(value))


def _time(value: datetime | None) -> str:
    return value.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S") if value else ""


class _Sheets:
    def __init__(self):
        self.book = Workbook()
        self.book.remove(self.book.active)
        self.long_text = None
        self.long_count = 0

    def sheet(self, title: str, headers: list[str], widths: list[int]):
        sheet = self.book.create_sheet(title)
        self.append(sheet, headers)
        sheet.freeze_panes = "A2"
        sheet.sheet_view.showGridLines = False
        for cell in sheet[1]:
            cell.font = Font(name="Microsoft YaHei", bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="254EDB")
        sheet.row_dimensions[1].height = 30
        for index, width in enumerate(widths, 1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        return sheet

    def append(self, sheet, values: list[Any]):
        row_number = sheet.max_row + 1 if sheet.max_row > 1 or sheet.cell(1, 1).value is not None else 1
        for column, value in enumerate(values, 1):
            cell = sheet.cell(row_number, column)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cell.value = value
            else:
                text = _text(value)
                # 15k Unicode code points also fit Excel's UTF-16 cell limit.
                if len(text) > 15000:
                    if self.long_text is None:
                        self.long_text = self.sheet("长文本", ["引用编号", "字段位置", "分段", "完整内容"],
                                                    [20, 40, 12, 100])
                    self.long_count += 1
                    ref = f"TEXT-{self.long_count:04d}"
                    for start in range(0, len(text), 15000):
                        self.append(self.long_text, [ref, f"{sheet.title}!{cell.coordinate}",
                                                    start // 15000 + 1, text[start:start + 15000]])
                    text = text[:200] + f"\n完整内容见「长文本」：{ref}（按分段顺序拼接）"
                cell.value = text
                cell.data_type = "s"  # Untrusted titles/quotes must never become executable formulas.
                cell.number_format = "@"
            cell.font = Font(name="Microsoft YaHei", size=11)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if row_number > 1 and row_number % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="F1F5FC")
        if row_number > 1:
            sheet.row_dimensions[row_number].height = 60

    def save(self) -> bytes:
        for sheet in self.book:
            sheet.auto_filter.ref = sheet.dimensions
        output = BytesIO()
        self.book.save(output)
        self.book.close()
        return output.getvalue()


def render_excel(jobs: list[ReviewJob], *, batch_id: str | None = None, total: int | None = None) -> bytes:
    writer = _Sheets()
    summary = writer.sheet("评审汇总", ["用例编号", "用例标题", "任务状态", "AI结论", "人工审批状态",
        "报告完整性", "发现数量", "阻断数量", "重要数量", "建议数量", "评审ID", "来源工作表", "来源行",
        "提交时间（北京时间）", "完成时间（北京时间）", "知识版本", "说明"],
        [26, 42, 25, 40, 20, 20, 12, 12, 12, 12, 40, 24, 20, 24, 24, 40, 50])
    steps = writer.sheet("用例步骤", ["用例编号", "用例标题", "前置条件", "步骤编号", "操作步骤", "预期结果", "测试数据"],
                         [26, 40, 55, 12, 75, 65, 55])
    issues = writer.sheet("问题明细", ["用例编号", "用例标题", "问题编号", "步骤编号", "维度", "严重程度", "类别",
        "问题状态", "原文引用", "问题说明", "修改建议", "知识依据是否验证", "证据状态", "知识引用ID", "投票情况", "评审ID"],
        [26, 40, 12, 12, 20, 14, 20, 18, 65, 80, 80, 24, 22, 50, 45, 40])
    sources = writer.sheet("知识依据", ["用例编号", "知识引用ID", "文档编号", "标题路径", "来源位置", "知识原文"],
                           [26, 50, 26, 45, 65, 100])
    notes = writer.sheet("导出说明", ["项目", "内容"], [32, 110])
    writer.append(notes, ["导出时间（北京时间）", _time(datetime.now(UTC))])
    writer.append(notes, ["导出范围", f"批次 {batch_id}" if batch_id else "单条评审"])
    writer.append(notes, ["用例总数", total if total is not None else len(jobs)])
    writer.append(notes, ["结果含义", "AI结论是评审意见，不等于人工审批；零发现不等于用例已被批准。"])
    writer.append(notes, ["当前进度快照", "未完成、失败、取消和缺少任务的用例均保留状态；空白数量不表示零问题。"])
    writer.append(notes, ["原始记录", "导出只读取已保存用例和报告，不重新调用模型，不修改评审结论。"
                         "人工审批列为导出时状态。"])
    writer.append(notes, ["数量口径", "按原报告所有发现统计，包含待复核或不采纳项，不代表最终采纳数量。"])
    writer.append(notes, ["表格内容", "原始文本作为文本单元格写入；不可显示的控制字符转义。"
                         "超长内容另存于长文本表，不截断。"])
    for job in sorted(jobs, key=lambda item: (item.created_at, item.id)):
        report = job.report_json or {}
        case = job.request_payload.get("case") or job.normalized_case or {}
        findings = report.get("issues", [])
        title = case.get("title") or job.case_title or report.get("title") or ""
        source = (case.get("test_data") or {}).get("excel_source", {}) if isinstance(case.get("test_data"), dict) else {}
        complete = (report.get("review_completeness") or {}).get("complete")
        label = "完整" if complete is True else "未完成/不完整" if report else "报告未生成"
        counts = [len(findings)] + [sum(x.get("severity") == severity for x in findings)
                                   for severity in ("blocker", "major", "suggestion")]
        if not report:
            counts = [None] * 4
        reasons = list(report.get("degraded_reasons") or job.degraded_reasons)
        if job.status == "failed":
            reasons.append("任务失败，请在页面查看任务状态后处理；未导出内部错误日志。")
        writer.append(summary, [job.case_id, title, STATUSES.get(job.status, job.status),
            VERDICTS.get(report.get("ai_verdict"), "未形成结论"), HUMAN.get(job.human_status, job.human_status),
            label, *counts, job.id, source.get("sheet"), ", ".join(map(str, source.get("rows", []))),
            _time(job.created_at), _time(job.finished_at), report.get("versions", {}).get("kb") or job.kb_build_version,
            "\n".join(reasons)])
        conditions = case.get("preconditions") or []
        conditions = "\n".join(map(str, conditions)) if isinstance(conditions, list) else str(conditions)
        authored_steps = case.get("steps") or [{"action": case.get("raw_text") or "未提供步骤", "expected": None}]
        for step in authored_steps:
            writer.append(steps, [job.case_id, title, conditions, step.get("index"), step.get("action"),
                                  step.get("expected"), case.get("test_data")])
        for item in findings:
            writer.append(issues, [job.case_id, title, item.get("issue_no"), item.get("step_index"),
                {"business": "业务", "test_design": "测试设计", "automation": "自动化"}.get(
                    item.get("dimension"), item.get("dimension")),
                SEVERITY.get(item.get("severity"), item.get("severity")), item.get("category"),
                ISSUE_STATUS.get(item.get("status"), item.get("status")), item.get("evidence_quote"),
                item.get("rationale"), item.get("suggestion"), "是" if item.get("kb_grounded") else "否",
                item.get("evidence_status"), item.get("kb_refs"), item.get("votes"), job.id])
        for source in (report.get("appendix", {}).get("knowledge_pack") or {}).get("evidence", []):
            writer.append(sources, [job.case_id, source.get("chunk_id"), source.get("doc_id"),
                                    source.get("heading_path"), source.get("source_ref"), source.get("text")])
    if total is not None and total > len(jobs):
        for index in range(total - len(jobs)):
            writer.append(summary, [f"未创建任务-{index + 1}", "", "任务尚未创建", "未形成结论", "", "报告未生成",
                                    None, None, None, None, "", "", "", "", "", "", "请查看批次状态，不能视为评审完成"])
    return writer.save()
