"""Rubric 契约检查：Schema、业务约束、冻结版本、与 docs/05・docs/17・报告 Schema 一致。

对应 docs/28 §3.2（P0-2 检查项）与 rubric/README.md 的 CI 规则。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_lib as lib
from contract_lib import Reporter, rel

CHECK = "rubric"
RUBRIC_PATH = lib.RUBRIC_DIR / "rubric.yaml"
SCHEMA_PATH = lib.RUBRIC_DIR / "schema.json"
PROMPT_DOC = lib.DOCS_DIR / "05-Prompt草案.md"
DICT_DOC = lib.DOCS_DIR / "17-全局数据字典.md"
REPORT_SCHEMA = lib.SCHEMAS_DIR / "report.schema.json"
README = lib.RUBRIC_DIR / "README.md"
BIZ_DOC = lib.DOCS_DIR / "00-业务定位与范围.md"
STANDARD_DOC = lib.DOCS_DIR / "04-评审标准.md"


def _section(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(end_marker, start + len(start_marker))
    return text[start : end if end > 0 else len(text)]


def _table_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or set(cells[0]) <= set("-: "):
            continue
        if cells[0] in ("#", "代码", "ID"):
            continue
        rows.append(cells)
    return rows


def _check_business_dimensions(data: dict[str, Any], reporter: Reporter) -> None:
    """校验 docs/00 §5.2 的 11 个业务维度与 docs/04 §2.1 映射、Rubric 检查点/分类一致。"""
    biz_text = lib.read_text(BIZ_DOC)
    dimension_block = _section(biz_text, "### 5.2 v1 评审维度", "### 5.3")
    dimensions = re.findall(r"^\d+\.\s+\*\*(.+?)\*\*：", dimension_block, re.M)
    if len(dimensions) != 11:
        reporter.error(
            CHECK,
            rel(BIZ_DOC),
            "§5.2",
            f"应有 11 个业务评审维度，实际解析到 {len(dimensions)} 个: {dimensions}",
        )

    standard_text = lib.read_text(STANDARD_DOC)
    mapping_block = _section(standard_text, "### 2.1 业务评审维度映射", "## 3. 检查点清单")
    rows = [row for row in _table_rows(mapping_block) if row and row[0].isdigit()]
    mapped = [row[1] for row in rows if len(row) > 1]
    if mapped != dimensions:
        missing = [item for item in dimensions if item not in mapped]
        extra = [item for item in mapped if item not in dimensions]
        reporter.error(
            CHECK,
            rel(STANDARD_DOC),
            "§2.1 业务维度映射",
            f"与 docs/00 §5.2 不一致：缺少 {missing}，多出 {extra}",
        )
    if len(rows) != 11:
        reporter.error(CHECK, rel(STANDARD_DOC), "§2.1 业务维度映射", f"应为 11 行，实际 {len(rows)} 行")

    checkpoint_ids = {
        checkpoint.get("id")
        for spec in data.get("dimensions", {}).values()
        for checkpoint in spec.get("checkpoints", [])
    }
    categories = set(data.get("categories", {}))
    for row in rows:
        label = row[0]
        checkpoints = set(re.findall(r"[BTA]\d{1,2}", row[2] if len(row) > 2 else ""))
        if not checkpoints:
            reporter.error(CHECK, rel(STANDARD_DOC), f"维度 {label}", "未映射任何 Rubric 检查点")
        unknown = sorted(checkpoints - checkpoint_ids)
        if unknown:
            reporter.error(CHECK, rel(STANDARD_DOC), f"维度 {label}", f"映射了不存在的检查点: {unknown}")
        used_categories = set(re.findall(r"`([^`]+)`", row[3] if len(row) > 3 else ""))
        unknown_categories = sorted(used_categories - categories)
        if unknown_categories:
            reporter.error(CHECK, rel(STANDARD_DOC), f"维度 {label}", f"映射了不存在的分类: {unknown_categories}")

    # docs/04 §5 的分类表必须与 Rubric 分类一致（数量、名称、顺序）
    category_block = _section(standard_text, "## 5. 问题分类（category 枚举）", "## 6. 各角色权重")
    doc_categories = []
    for row in _table_rows(category_block):
        match = re.fullmatch(r"`([^`]+)`", row[0])
        if match:
            doc_categories.append(match.group(1))
    rubric_categories = list(data.get("categories", {}))
    if doc_categories != rubric_categories:
        reporter.error(
            CHECK,
            rel(STANDARD_DOC),
            "§5 分类表",
            f"与 rubric.yaml 不一致：文档 {doc_categories}，Rubric {rubric_categories}",
        )


def _validate_schema(data: dict[str, Any], reporter: Reporter) -> None:
    """Rubric 结构必须通过 schema.json（jsonschema Draft 2020-12）。"""
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - 环境缺少依赖时明确失败
        reporter.error(CHECK, rel(SCHEMA_PATH), "dependency", "缺少 jsonschema，无法执行 Rubric Schema 校验")
        return

    schema = lib.load_json(SCHEMA_PATH, reporter, CHECK)
    validator = jsonschema.Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
        path = "/".join(str(part) for part in error.absolute_path) or "<root>"
        reporter.error(CHECK, rel(RUBRIC_PATH), path, f"Schema 校验失败: {error.message}")


def _check_version_and_copy(data: dict[str, Any], reporter: Reporter) -> None:
    version = str(data.get("version", ""))
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        reporter.error(CHECK, rel(RUBRIC_PATH), "version", f"必须为 SemVer X.Y.Z，实际 {version!r}")
    if data.get("status") not in ("draft", "reviewed", "published", "deprecated"):
        reporter.error(CHECK, rel(RUBRIC_PATH), "status", f"非法状态: {data.get('status')!r}")

    copy_path = lib.RUBRIC_DIR / "versions" / f"v{version}.yaml"
    if not copy_path.exists():
        reporter.error(CHECK, rel(copy_path), "versions", "缺少当前版本的冻结副本")
    else:
        copy = lib.load_yaml(copy_path, reporter, CHECK)
        if copy != data:
            reporter.error(CHECK, rel(copy_path), "versions", "冻结副本与 rubric.yaml 内容不一致（改规则必须递增版本）")

    lines = lib.read_lines(README)
    if not any(version in line and line.strip().startswith("|") for line in lines):
        reporter.error(CHECK, rel(README), "版本表", f"README 版本表缺少 {version} 行")

    # 验收/设计文件不得硬编码 Rubric 版本（补充 15 P0-1）
    for path in sorted(lib.DESIGN_DIR.glob("*.yaml")):
        text = lib.read_text(path)
        for match in re.finditer(r"versions/v(\d+\.\d+\.\d+)\.yaml", text):
            reporter.error(
                CHECK,
                rel(path),
                "Rubric 版本绑定",
                f"不得硬编码 v{match.group(1)}；应从 rubric.version 读取并定位副本（当前 {version}）",
            )


def _check_business(data: dict[str, Any], reporter: Reporter) -> None:
    dimensions = data.get("dimensions", {})
    checkpoints: dict[str, str] = {}
    for dimension, spec in dimensions.items():
        for checkpoint in spec.get("checkpoints", []):
            cid = checkpoint.get("id")
            if cid in checkpoints:
                reporter.error(
                    CHECK,
                    rel(RUBRIC_PATH),
                    f"checkpoint {cid}",
                    f"ID 重复（{checkpoints[cid]} 与 {dimension}）",
                )
            checkpoints[cid] = dimension

    for category, spec in data.get("categories", {}).items():
        for dimension in spec.get("dimensions", []):
            if dimension not in dimensions:
                reporter.error(
                    CHECK, rel(RUBRIC_PATH), f"category {category}", f"引用未定义维度 {dimension!r}"
                )

    fusion = data.get("fusion", {})
    suspect = fusion.get("cosine_suspect")
    high = fusion.get("cosine_high")
    if not isinstance(suspect, (int, float)) or not isinstance(high, (int, float)):
        reporter.error(CHECK, rel(RUBRIC_PATH), "fusion", "cosine 阈值必须是数值")
    elif not (0 <= suspect < high <= 1):
        reporter.error(
            CHECK,
            rel(RUBRIC_PATH),
            "fusion",
            f"必须满足 0 ≤ cosine_suspect({suspect}) < cosine_high({high}) ≤ 1",
        )

    voting = data.get("voting", {})
    if voting.get("min_valid_votes_per_candidate") != 2:
        reporter.error(
            CHECK,
            rel(RUBRIC_PATH),
            "voting.min_valid_votes_per_candidate",
            f"必须与 docs/12 §6 的 2 票一致，实际 {voting.get('min_valid_votes_per_candidate')!r}",
        )
    if voting.get("severity_gap_for_human") != 2:
        reporter.error(
            CHECK,
            rel(RUBRIC_PATH),
            "voting.severity_gap_for_human",
            f"必须与 docs/12 §3 的跨两级一致，实际 {voting.get('severity_gap_for_human')!r}",
        )

    dict_lines = lib.read_lines(DICT_DOC)
    checks = [
        ("issues.severity", set(data.get("severity", {})), True),
        ("issue_votes.validity", set(voting.get("validity_states", [])), False),
        ("evidence_status", set(data.get("evidence", {}).get("status", [])), False),
    ]
    for key, actual, is_mapping in checks:
        expected = lib.dictionary_enum(dict_lines, key)
        if expected is None:
            reporter.error(CHECK, rel(DICT_DOC), key, "字典中找不到该枚举")
            continue
        expected_set = {value for value in expected if value is not None}
        if expected_set != actual:
            reporter.error(
                CHECK,
                rel(RUBRIC_PATH),
                key,
                f"与 docs/17 不一致：字典 {sorted(expected_set)}，Rubric {sorted(actual)}",
            )


def _check_prompt_references(data: dict[str, Any], reporter: Reporter) -> None:
    text = lib.read_text(PROMPT_DOC)
    lines = text.splitlines()

    category_match = re.search(r'"category":\s*"([^"]+)"', text)
    if not category_match:
        reporter.error(CHECK, rel(PROMPT_DOC), "category", "未找到 Prompt 的 category 枚举")
    else:
        prompt_categories = category_match.group(1).split("|")
        rubric_categories = list(data.get("categories", {}))
        if prompt_categories != rubric_categories:
            missing = [item for item in rubric_categories if item not in prompt_categories]
            extra = [item for item in prompt_categories if item not in rubric_categories]
            reporter.error(
                CHECK,
                rel(PROMPT_DOC),
                "category",
                f"与 rubric.yaml 不一致：缺少 {missing}，多出 {extra}",
            )

    severity_match = re.search(r'"severity":\s*"([^"]+)"', text)
    if severity_match:
        prompt_severity = severity_match.group(1).split("|")
        if set(prompt_severity) != set(data.get("severity", {})):
            reporter.error(
                CHECK,
                rel(PROMPT_DOC),
                "severity",
                f"与 rubric.yaml 不一致：Prompt {sorted(prompt_severity)}，Rubric {sorted(data.get('severity', {}))}",
            )

    checkpoint_ids = {
        checkpoint.get("id")
        for spec in data.get("dimensions", {}).values()
        for checkpoint in spec.get("checkpoints", [])
    }
    referenced = set(re.findall(r"(?<![A-Za-z0-9])([BTA][1-9])(?![0-9A-Za-z])", text))
    unknown = sorted(referenced - checkpoint_ids)
    if unknown:
        reporter.error(CHECK, rel(PROMPT_DOC), "checkpoints", f"Prompt 引用了不存在的 checkpoint: {unknown}")
    unused = sorted(checkpoint_ids - referenced)
    if unused:
        reporter.warn(CHECK, rel(RUBRIC_PATH), "checkpoints", f"checkpoint 未被任何 Prompt 引用: {unused}")


def _check_report_schema(data: dict[str, Any], reporter: Reporter) -> None:
    schema = lib.load_json(REPORT_SCHEMA, reporter, CHECK)
    issue = schema.get("$defs", {}).get("issue", {})
    report_severity = set(issue.get("properties", {}).get("severity", {}).get("enum", []))
    rubric_severity = set(data.get("severity", {}))
    if report_severity != rubric_severity:
        reporter.error(
            CHECK,
            rel(REPORT_SCHEMA),
            "issue.severity",
            f"报告 Schema {sorted(report_severity)} 与 Rubric {sorted(rubric_severity)} 不一致",
        )

    evidence = set(issue.get("properties", {}).get("evidence_status", {}).get("enum", [])) - {None}
    rubric_evidence = set(data.get("evidence", {}).get("status", []))
    if evidence != rubric_evidence:
        reporter.error(
            CHECK,
            rel(REPORT_SCHEMA),
            "issue.evidence_status",
            f"报告 Schema {sorted(evidence)} 与 Rubric {sorted(rubric_evidence)} 不一致",
        )


def run(reporter: Reporter) -> None:
    reporter.checks_run += 1
    if not RUBRIC_PATH.exists():
        reporter.error(CHECK, rel(RUBRIC_PATH), "file", "文件不存在")
        return
    data = lib.load_yaml(RUBRIC_PATH, reporter, CHECK)
    if not isinstance(data, dict):
        reporter.error(CHECK, rel(RUBRIC_PATH), "root", "顶层必须是对象")
        return

    reporter.checks_run += 1
    _validate_schema(data, reporter)
    _check_version_and_copy(data, reporter)
    _check_business(data, reporter)
    _check_business_dimensions(data, reporter)
    _check_prompt_references(data, reporter)
    _check_report_schema(data, reporter)

    if data.get("status") != "published":
        reporter.note(
            f"Rubric 状态为 {data.get('status')!r}：按 rubric/README 与 docs/08 §7，生产模式必须使用 published 版本"
        )


def main() -> int:
    reporter = Reporter()
    run(reporter)
    return lib.print_report(reporter, title="Rubric 契约检查", verbose=True)


if __name__ == "__main__":
    raise SystemExit(main())
