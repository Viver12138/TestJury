from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.core.errors import ApiError
from app.services.excel_import import MAX_BYTES, parse_workbook, template_workbook


def workbook(rows, *, merge=False):
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    if merge:
        sheet.merge_cells("A2:A3")
        sheet.merge_cells("B2:B3")
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def test_merged_multiline_and_blank_expected_preserve_source():
    data = workbook([
        ["用例编号", "用例名称", "前置条件", "测试步骤", "预期结果"],
        ["TC-1", "查看订单", "用户已登录", "打开订单", "显示订单"],
        [None, None, None, "打开详情", None],
        ["TC-2", "支付订单", None, "1.创建订单\n2.支付", "1.创建成功\n2.支付成功"],
    ], merge=True)
    result = parse_workbook(data, "cases.xlsx")
    assert result["total"] == 2
    case = result["cases"][0]
    assert case["steps"][1] == {"index": 2, "action": "打开详情", "expected": None}
    assert case["preconditions"] == ["用户已登录"]
    assert case["test_data"]["excel_source"]["rows"] == [2, 3]
    assert len(result["cases"][1]["steps"]) == 2
    assert result["warnings"]
    assert parse_workbook(data, "renamed.xlsx")["cases"] == result["cases"]


def test_unmatched_multiline_is_not_arbitrarily_paired():
    result = parse_workbook(workbook([["标题", "步骤", "预期"], ["测试", "打开\n保存", "成功"]]), "a.xlsx")
    assert result["cases"][0]["steps"] == [{"index": 1, "action": "打开\n保存", "expected": "成功"}]


@pytest.mark.parametrize(("rows", "message"), [
    ([["标题", "预期"], ["测试", "成功"]], "未找到"),
    ([["标题", "步骤"], [None, "操作"]], "缺少用例标题"),
    ([["标题", "步骤"], ["测试", None]], "缺少操作步骤"),
    ([["用例编号", "标题", "步骤"], ["A", "甲", "操作"], ["B", "乙", "操作"], ["A", "甲", "操作"]], "编号重复"),
    ([["标题", "用例标题", "步骤"], ["测试", "测试", "操作"]], "重复含义"),
    ([["标题", "步骤"], ["测试", "=1+1"]], "包含公式"),
    ([["标题", "步骤"]] + [[f"测试{i}", "操作"] for i in range(51)], "最多上传 50"),
])
def test_invalid_workbooks_fail_with_actionable_messages(rows, message):
    with pytest.raises(ApiError, match=message):
        parse_workbook(workbook(rows), "a.xlsx")


def test_corrupt_unsupported_oversized_and_empty_files():
    for data, filename in ((b"invalid", "a.xlsx"), (b"invalid", "a.xls"), (b"1", "a.csv"),
                           (b"x" * (MAX_BYTES + 1), "a.xlsx"), (b"", "a.xlsx")):
        with pytest.raises(ApiError):
            parse_workbook(data, filename)


def test_template_is_a_valid_complete_case():
    result = parse_workbook(template_workbook(), "template.xlsx")
    assert result["total"] == 1
    assert result["cases"][0]["project_id"] == "minishop"
    assert result["cases"][0]["steps"][0]["expected"]


def test_legacy_xls_import_retains_two_steps():
    data = (Path(__file__).parents[1] / "fixtures/excel/legacy.xls").read_bytes()
    result = parse_workbook(data, "legacy.xls")
    assert result["total"] == 1
    assert result["cases"][0]["case_id"] == "XLS-001"
    assert len(result["cases"][0]["steps"]) == 2
    assert result["cases"][0]["steps"][1]["expected"] == "支付成功"


def test_extra_columns_are_preserved_as_authored_test_data():
    result = parse_workbook(workbook([["标题", "步骤", "需求说明"], ["测试", "操作", "原始范围"]]), "a.xlsx")
    assert result["cases"][0]["test_data"]["extra_columns"][0]["values"] == {"需求说明": "原始范围"}


def test_header_after_heading_and_multiple_sheets_do_not_silently_drop_data():
    data = workbook([["评审用例清单"], [], ["标题", "步骤"], ["测试", "操作"]])
    assert parse_workbook(data, "a.xlsx")["locations"][0]["row"] == 4
    book = Workbook()
    book.active.append(["标题", "步骤"])
    book.active.append(["测试", "操作"])
    book.create_sheet("其他内容").append(["无法识别的数据"])
    output = BytesIO()
    book.save(output)
    with pytest.raises(ApiError, match="其他内容"):
        parse_workbook(output.getvalue(), "a.xlsx")
