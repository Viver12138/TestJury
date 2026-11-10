"""检查 M0 验收用例与 P0 契约清理用例的完整性、覆盖度与追踪字段。

对应 docs/28 §4（P0-3）：M0 十项退出条件 -> 验收用例 -> 自动化测试 -> CI Job。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_lib as lib
from contract_lib import Reporter, rel

CASES_PATH = lib.DESIGN_DIR / "m0_acceptance.yaml"
DOCS08 = lib.DOCS_DIR / "08-评审修订与实施计划.md"
CHECK = "m0-acceptance"
CASE_RE = re.compile(r"^ACC-(M0|CON|BIZ)-\d{3}$")
REQUIRED_CASE_KEYS = {
    "id",
    "maps_to",
    "title",
    "preconditions",
    "input",
    "steps",
    "expected",
    "failure_criteria",
    "automation",
    "test_file",
    "ci_job",
    "result",
}
RESULT_STATES = {"not_run", "passed", "failed", "blocked"}


def _non_empty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return len(value) > 0
    return value is not None


def _parse_docs08_m0(reporter: Reporter) -> list[tuple[str, str]]:
    """从 docs/08 §5.2 解析 M0 退出条件表，返回 [(module, requirement)]。"""
    text = lib.read_text(DOCS08)
    start = text.find("### 5.2 M0 开发准入与退出条件")
    if start < 0:
        reporter.error(CHECK, rel(DOCS08), "§5.2", "未找到 M0 退出条件章节")
        return []
    end = text.find("M0 不包含", start)
    section = text[start : end if end > 0 else len(text)]
    rows: list[tuple[str, str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if cells[0] in ("模块", "---") or set(cells[0]) <= set("-: "):
            continue
        rows.append((cells[0], cells[1]))
    return rows


def run(reporter: Reporter) -> None:
    reporter.checks_run += 1
    if not CASES_PATH.exists():
        reporter.error(CHECK, rel(CASES_PATH), "file", "文件不存在")
        return
    data = lib.load_yaml(CASES_PATH, reporter, CHECK)
    if not isinstance(data, dict):
        reporter.error(CHECK, rel(CASES_PATH), "root", "顶层必须是对象")
        return

    if not data.get("baseline"):
        reporter.error(CHECK, rel(CASES_PATH), "baseline", "缺少基线引用")

    jobs = {job.get("id") for job in data.get("ci_jobs", []) if job.get("id")}
    for job in data.get("ci_jobs", []):
        if not job.get("description"):
            reporter.error(CHECK, rel(CASES_PATH), f"ci_job {job.get('id')}", "缺少 description")

    conditions = data.get("exit_conditions", [])
    condition_ids = [item.get("id") for item in conditions]
    if len(condition_ids) != 10:
        reporter.error(CHECK, rel(CASES_PATH), "exit_conditions", f"M0 应有 10 项退出条件，实际 {len(condition_ids)}")
    if len(condition_ids) != len(set(condition_ids)):
        reporter.error(CHECK, rel(CASES_PATH), "exit_conditions", "退出条件 ID 重复")
    expected_ids = [f"M0-{index:02d}" for index in range(1, 11)]
    for expected in expected_ids:
        if expected not in condition_ids:
            reporter.error(CHECK, rel(CASES_PATH), expected, "缺少 M0 退出条件")
    for condition in conditions:
        for key in ("module", "requirement"):
            if not _non_empty(condition.get(key)):
                reporter.error(CHECK, rel(CASES_PATH), condition.get("id", "?"), f"缺少 {key}")

    contract_items = data.get("contract_items", [])
    contract_ids = [item.get("id") for item in contract_items]
    for expected in ("P0-1", "P0-2", "P0-3", "P0-4"):
        if expected not in contract_ids:
            reporter.error(CHECK, rel(CASES_PATH), expected, "缺少 P0 契约项")
    if len(contract_ids) != len(set(contract_ids)):
        reporter.error(CHECK, rel(CASES_PATH), "contract_items", "契约项 ID 重复")

    # docs/08 的 M0 表是事实源：模块顺序与文本必须一致
    doc_rows = _parse_docs08_m0(reporter)
    if doc_rows:
        doc_modules = [module for module, _ in doc_rows]
        yaml_modules = [condition.get("module") for condition in conditions]
        if doc_modules != yaml_modules:
            reporter.error(
                CHECK,
                rel(CASES_PATH),
                "exit_conditions.module",
                f"与 docs/08 §5.2 不一致：docs={doc_modules}，yaml={yaml_modules}",
            )

    cases = data.get("cases", [])
    if not cases:
        reporter.error(CHECK, rel(CASES_PATH), "cases", "用例列表为空")
        return

    seen: set[str] = set()
    covered: dict[str, int] = {}
    used_jobs: set[str] = set()
    for case in cases:
        cid = case.get("id", "<missing>")
        if not CASE_RE.match(cid):
            reporter.error(CHECK, rel(CASES_PATH), cid, "用例 ID 必须形如 ACC-M0-001 / ACC-CON-001 / ACC-BIZ-001")
        if cid in seen:
            reporter.error(CHECK, rel(CASES_PATH), cid, "用例 ID 重复")
        seen.add(cid)

        missing = REQUIRED_CASE_KEYS - set(case)
        if missing:
            reporter.error(CHECK, rel(CASES_PATH), cid, f"缺少字段: {sorted(missing)}")
            continue
        for key in REQUIRED_CASE_KEYS - {"id", "result"}:
            if not _non_empty(case.get(key)):
                reporter.error(CHECK, rel(CASES_PATH), f"{cid}.{key}", "不得为空")
        if case["result"] not in RESULT_STATES:
            reporter.error(CHECK, rel(CASES_PATH), f"{cid}.result", f"非法结果状态: {case['result']!r}")

        target = case["maps_to"]
        if target not in condition_ids and target not in contract_ids:
            reporter.error(CHECK, rel(CASES_PATH), f"{cid}.maps_to", f"引用未定义的退出条件/契约项: {target!r}")
        covered[target] = covered.get(target, 0) + 1

        ci_job = case["ci_job"]
        if ci_job not in jobs:
            reporter.error(CHECK, rel(CASES_PATH), f"{cid}.ci_job", f"未声明的 CI Job: {ci_job!r}")
        used_jobs.add(ci_job)

        test_file = case["test_file"]
        if not str(test_file).startswith("tests/"):
            reporter.error(CHECK, rel(CASES_PATH), f"{cid}.test_file", f"必须指向 tests/ 下的文件: {test_file!r}")

    for target in condition_ids + contract_ids:
        if not covered.get(target):
            reporter.error(CHECK, rel(CASES_PATH), target, "没有任何验收用例映射到该项")

    for job in jobs:
        if job not in used_jobs:
            reporter.error(CHECK, rel(CASES_PATH), f"ci_job {job}", "未被任何用例使用")

    reporter.note(
        f"M0 条件 {len(conditions)} 项 / 契约项 {len(contract_items)} 项 / 用例 {len(cases)} 条 / CI Job {len(jobs)} 个"
    )


def main() -> int:
    reporter = Reporter()
    run(reporter)
    return lib.print_report(reporter, title="M0 验收用例检查", verbose=True)


if __name__ == "__main__":
    raise SystemExit(main())
