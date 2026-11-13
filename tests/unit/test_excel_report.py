from copy import deepcopy
from io import BytesIO

from openpyxl import load_workbook

from app.services.excel_report import render_excel
from app.storage.models import ReviewJob


def job(identifier="TC-1", **kwargs):
    values = dict(id=identifier, case_id=identifier, case_version=1, module="order", test_type="functional",
                  test_type_source="request", status="done", stage="render", input_hash="h", idempotency_key=identifier,
                  request_payload={"case": {"title": "订单金额", "preconditions": ["已登录"],
                    "steps": [{"index": 1, "action": "下单", "expected": "支付200"}]}}, report_schema_version="report-1.0",
                  report_json={"ai_verdict": "conditional", "issues": [], "review_completeness": {"complete": True}})
    values.update(kwargs)
    return ReviewJob(**values)


def rows(sheet):
    content = list(sheet.values)
    return [dict(zip(content[0], row, strict=True)) for row in content[1:]]


def test_export_retains_case_issue_sources_and_separate_approval_without_mutation():
    negative = job(report_json={"ai_verdict": "blocked", "review_completeness": {"complete": True},
        "issues": [{"issue_no": 1, "step_index": 1, "severity": "blocker", "category": "规则冲突", "status": "adopted",
                    "evidence_quote": "支付0.01", "rationale": "金额冲突", "suggestion": "应付200", "kb_grounded": True}],
        "appendix": {"knowledge_pack": {"evidence": [{"chunk_id": "chunk", "doc_id": "RULE-1", "text": "服务端计价"}]}}})
    original = deepcopy(negative)
    book = load_workbook(BytesIO(render_excel([negative, job("TC-2")], batch_id="batch", total=2)))
    assert book.sheetnames == ["评审汇总", "用例步骤", "问题明细", "知识依据", "导出说明"]
    summary = rows(book["评审汇总"])
    assert summary[0]["AI结论"] == "存在阻断问题"
    assert summary[0]["人工审批状态"] == "待人工审批"
    assert summary[1]["发现数量"] == 0
    assert rows(book["问题明细"])[0]["修改建议"] == "应付200"
    assert rows(book["用例步骤"])[0]["前置条件"] == "已登录"
    assert rows(book["知识依据"])[0]["知识原文"] == "服务端计价"
    assert book["问题明细"].freeze_panes == "A2" and book["问题明细"].auto_filter.ref
    assert negative == original


def test_pending_failed_cancelled_and_missing_tasks_are_not_exported_as_clean():
    jobs = [job("Q", status="queued", report_json=None), job("F", status="failed", report_json=None),
            job("C", status="cancelled", report_json=None)]
    book = load_workbook(BytesIO(render_excel(jobs, batch_id="b", total=4)))
    records = rows(book["评审汇总"])
    assert len(records) == 4
    assert all(r["发现数量"] is None and r["AI结论"] == "未形成结论" for r in records)
    assert {r["任务状态"] for r in records} == {"等待评审", "评审失败", "已取消", "任务尚未创建"}
    assert rows(book["问题明细"]) == []


def test_untrusted_formulas_and_excel_error_tokens_are_literal_text():
    item = job()
    item.request_payload["case"].update(title='=HYPERLINK("https://example.invalid","click")',
                                       preconditions=["+cmd", "@SUM(1)", "#N/A", "control\x01text"])
    book = load_workbook(BytesIO(render_excel([item])))
    assert book["评审汇总"]["B2"].value.startswith("=HYPERLINK")
    assert book["评审汇总"]["B2"].data_type == "s"
    assert "control\\u0001text" in book["用例步骤"]["C2"].value
    assert all(cell.data_type != "f" for sheet in book for row in sheet for cell in row)


def test_long_unicode_text_is_exported_losslessly_in_numbered_chunks():
    long_text = "订单😀" * 14000
    item = job()
    item.request_payload["case"]["steps"][0]["expected"] = long_text
    book = load_workbook(BytesIO(render_excel([item])))
    assert "长文本" in book.sheetnames
    pieces = rows(book["长文本"])
    assert "".join(r["完整内容"] for r in pieces) == long_text
    assert all(len(r["完整内容"].encode("utf-16-le")) // 2 <= 32767 for r in pieces)
    assert "TEXT-0001" in book["用例步骤"]["F2"].value


def test_incomplete_report_retains_partial_findings_without_becoming_complete():
    item = job(report_json={"ai_verdict": "need_human", "review_completeness": {"complete": False}, "issues": []})
    record = rows(load_workbook(BytesIO(render_excel([item])))["评审汇总"])[0]
    assert record["报告完整性"] == "未完成/不完整"
    assert record["AI结论"] == "需要复核"
