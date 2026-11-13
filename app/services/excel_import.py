"""Bounded Excel import; preserve authored steps and never execute workbook content."""

from __future__ import annotations

import hashlib
import re
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook

from app.core.errors import ApiError, ErrorCode

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 5000
MAX_COLS = 100
MAX_CASES = 50
ALIASES = {
    "case_id": ("用例编号", "用例id", "编号", "case_id", "id"),
    "title": ("用例标题", "用例名称", "测试用例", "测试用例名称", "标题", "title"),
    "action": ("操作步骤", "测试步骤", "执行步骤", "步骤描述", "步骤", "操作", "action", "steps"),
    "expected": ("预期结果", "期望结果", "预期输出", "预期", "期望", "expected"),
    "preconditions": ("前置条件", "前提条件", "前置", "预置条件", "preconditions"),
    "module": ("模块", "所属模块", "功能模块", "module"),
    "project_id": ("项目id", "项目编号", "project_id"),
    "product_version": ("产品版本", "product_version"),
    "test_data": ("测试数据", "test_data"),
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _header(value: Any) -> str:
    return re.sub(r"[\s*：:]", "", _text(value)).casefold()


HEADERS = {_header(alias): field for field, aliases in ALIASES.items() for alias in aliases}


def _invalid(message: str) -> None:
    raise ApiError(ErrorCode.INPUT_INVALID, message, field="file")


def _xlsx(data: bytes) -> list[tuple[str, list[list[str]]]]:
    with ZipFile(BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 2000 or sum(x.file_size for x in entries) > 30 * 1024 * 1024:
            _invalid("工作簿解压后过大，请拆分文件")
    book = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
    result = []
    try:
        if len(book.worksheets) > 20:
            _invalid("单个工作簿最多 20 张工作表，请拆分")
        total_rows = 0
        for sheet in book:
            if sheet.sheet_state != "visible":
                _invalid(f"工作表「{sheet.title}」已隐藏，请删除或取消隐藏后上传")
            if (sheet.max_row or 0) > MAX_ROWS or (sheet.max_column or 0) > MAX_COLS:
                _invalid(f"工作表「{sheet.title}」超过 5000 行或 100 列，请删除多余区域或拆分")
            # Do not trust a producer's understated worksheet dimensions.
            sheet.reset_dimensions()
            rows = []
            for number, cells in enumerate(sheet.iter_rows(max_col=MAX_COLS + 1), 1):
                total_rows += 1
                if total_rows > MAX_ROWS:
                    _invalid("工作簿总行数超过 5000，请拆分")
                if number > MAX_ROWS or _text(cells[-1].value):
                    _invalid(f"工作表「{sheet.title}」超过行列限制")
                row = []
                for cell in cells[:-1]:
                    if cell.data_type == "f":
                        _invalid(f"工作表「{sheet.title}」第 {number} 行包含公式，请粘贴为值后上传")
                    row.append(_text(cell.value))
                rows.append(row)
            result.append((sheet.title, rows))
    finally:
        book.close()
    return result


def _xls(data: bytes) -> list[tuple[str, list[list[str]]]]:
    import xlrd

    book = xlrd.open_workbook(file_contents=data, on_demand=True)
    result = []
    try:
        if book.nsheets > 20:
            _invalid("单个工作簿最多 20 张工作表，请拆分")
        total_rows = 0
        for sheet in book.sheets():
            if sheet.visibility:
                _invalid(f"工作表「{sheet.name}」已隐藏，请删除或取消隐藏后上传")
            if sheet.nrows > MAX_ROWS or sheet.ncols > MAX_COLS:
                _invalid(f"工作表「{sheet.name}」超过 5000 行或 100 列，请拆分")
            total_rows += sheet.nrows
            if total_rows > MAX_ROWS:
                _invalid("工作簿总行数超过 5000，请拆分")
            result.append((sheet.name, [[_text(c.value) for c in sheet.row(row)] for row in range(sheet.nrows)]))
    finally:
        book.release_resources()
    return result


def parse_workbook(data: bytes, filename: str) -> dict[str, Any]:
    if not data or len(data) > MAX_BYTES:
        _invalid("请选择非空 Excel 文件，文件大小不能超过 10 MB")
    suffix = Path(filename).suffix.casefold()
    if suffix not in {".xlsx", ".xls"}:
        _invalid("仅支持 .xlsx 或 .xls 文件，请在 Excel 中另存为这两种格式")
    try:
        sheets = _xlsx(data) if suffix == ".xlsx" else _xls(data)
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(ErrorCode.INPUT_INVALID, "无法读取工作簿，请确认文件未损坏、未加密且格式正确", field="file") from exc
    digest = hashlib.sha256(data).hexdigest()
    cases: list[dict[str, Any]] = []
    locations = []
    warnings = []
    seen_ids: set[str] = set()
    for sheet_index, (name, rows) in enumerate(sheets, 1):
        if not any(any(row) for row in rows):
            continue
        mapping = {}
        start = None
        for i, row in enumerate(rows[:20]):
            fields = [HEADERS.get(_header(cell)) for cell in row]
            if "title" in fields and "action" in fields:
                present = [f for f in fields if f]
                if len(present) != len(set(present)):
                    _invalid(f"工作表「{name}」有重复含义的列名，请保留一列")
                mapping = {field: col for col, field in enumerate(fields) if field}
                start = i + 1
                break
        if start is None:
            _invalid(f"工作表「{name}」前 20 行未找到「用例标题」和「操作步骤」列，请参考模板")
        current = None
        extra_columns = {col: label for col, label in enumerate(rows[start - 1])
                         if label and col not in mapping.values()}
        for number, row in enumerate(rows[start:], start + 1):
            if not any(row):
                current = None
                continue
            values = {field: row[col] if col < len(row) else "" for field, col in mapping.items()}
            if sum(map(len, row)) > 20000:
                _invalid(f"工作表「{name}」第 {number} 行内容过长")
            title, identifier = values.get("title"), values.get("case_id")
            continuation = current is not None and (
                (not title and (not identifier or identifier == current["case_id"]))
                or (identifier and identifier == current["case_id"] and title == current["title"]))
            if not continuation:
                if not title:
                    _invalid(f"工作表「{name}」第 {number} 行缺少用例标题，且不能归入上一条用例")
                identifier = identifier or f"EXCEL-{digest[:12]}-{sheet_index}-{number}"
                if identifier in seen_ids:
                    _invalid(f"工作表「{name}」第 {number} 行用例编号重复，请将同一用例的步骤连续放置")
                seen_ids.add(identifier)
                if len(cases) >= MAX_CASES:
                    _invalid("单次最多上传 50 条用例，请拆分工作簿")
                current = {
                    "case_id": identifier, "case_version": 1, "title": title,
                    "module": values.get("module") or "order", "project_id": values.get("project_id") or "minishop",
                    "product_version": values.get("product_version") or "1.0.0", "platform": "api",
                    "review_baseline": "current_implementation", "test_type": "functional", "source": "manual",
                    "preconditions": [], "steps": [],
                    "test_data": {"excel_source": {"file_sha256": digest, "sheet": name, "rows": []}},
                }
                cases.append(current)
                locations.append({"sheet": name, "row": number, "case_id": identifier})
            assert current is not None
            for field in ("module", "project_id", "product_version"):
                if values.get(field) and values[field] != current[field]:
                    _invalid(f"工作表「{name}」第 {number} 行的 {field} 与该用例前面步骤不一致")
            action, expected = values.get("action", ""), values.get("expected", "")
            if not action:
                _invalid(f"工作表「{name}」第 {number} 行缺少操作步骤")
            current["test_data"]["excel_source"]["rows"].append(number)
            extras = {label: row[col] for col, label in extra_columns.items() if col < len(row) and row[col]}
            if extras:
                current["test_data"].setdefault("extra_columns", []).append({"row": number, "values": extras})
            if values.get("test_data"):
                current["test_data"].setdefault("authored", []).append(values["test_data"])
            for condition in values.get("preconditions", "").splitlines():
                if condition.strip() and condition.strip() not in current["preconditions"]:
                    current["preconditions"].append(condition.strip())
            actions, expectations = action.splitlines(), expected.splitlines()
            pairs = (list(zip(actions, expectations, strict=True))
                     if len(actions) == len(expectations) > 1 and all(actions) and all(expectations)
                     else [(action, expected)])
            for operation, outcome in pairs:
                current["steps"].append({"index": len(current["steps"]) + 1,
                                         "action": operation, "expected": outcome or None})
            if len(current["steps"]) > 200 or len(str(current)) > 20000:
                _invalid(f"工作表「{name}」第 {number} 行所在用例过长，请拆分")
            if not expected:
                warnings.append(f"{name} 第 {number} 行未填写预期结果，将作为待评审内容保留")
    if not cases:
        _invalid("工作簿中没有可评审用例")
    if suffix == ".xls":
        warnings.append("旧版 .xls 中的公式按已保存结果读取；如有公式，请先在 Excel 中重新计算并保存")
    return {"filename": Path(filename).name, "sha256": digest, "total": len(cases),
            "cases": cases, "locations": locations, "warnings": warnings}


def template_workbook() -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "测试用例"
    sheet.append(["用例编号", "用例标题", "前置条件", "操作步骤", "预期结果"])
    sheet.append(["TC-001", "客户端修改金额后按服务端重新计价",
                  "独立测试库；用户A已登录；地址1属于A；SKU1有效、上架、单价100、库存10；无券",
                  "POST /api/orders，items=[{sku_id:1,quantity:2}],address_id=1,pay_amount=0.01",
                  "HTTP 201；data.pay_amount=200"])
    sheet.freeze_panes = "A2"
    from openpyxl.styles import Alignment, Font, PatternFill

    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="254EDB")
    for row in sheet:
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for column, width in zip("ABCDE", (18, 34, 52, 65, 40), strict=True):
        sheet.column_dimensions[column].width = width
    sheet.row_dimensions[2].height = 75
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()
