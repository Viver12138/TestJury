"""跨文档契约检查：索引/版本/枚举/幂等口径/决策索引/README 决策表/Schema 版本。

对应 docs/28 §3.1（P0-2）与 docs/08 §2.0.1 的唯一事实源约定。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_lib as lib
from contract_lib import Reporter, rel

CHECK = "docs"
README = lib.ROOT / "README.md"
DICT_DOC = lib.DOCS_DIR / "17-全局数据字典.md"
BIZ_DOC = lib.DOCS_DIR / "00-业务定位与范围.md"
DOCS08 = lib.DOCS_DIR / "08-评审修订与实施计划.md"
API_DOC = lib.DOCS_DIR / "03-API契约.md"
ARCH_DOC = lib.DOCS_DIR / "01-架构设计.md"
DATA_DOC = lib.DOCS_DIR / "02-数据模型.md"
ERROR_DOC = lib.DOCS_DIR / "19-API错误码与契约.md"
SCHEMA = lib.SCHEMAS_DIR / "report.schema.json"
SCHEMA_FROZEN = lib.SCHEMAS_DIR / "versions" / "report-1.0.schema.json"
DECISIONS = lib.DESIGN_DIR / "decisions.yaml"
SCRIPTS = lib.ROOT / "scripts"

STATUS_VALUES = {"decided", "pending_confirmation", "pending_validation", "implemented", "verified"}
VALIDATION_VALUES = {"pending", "passed", "failed"}
IMPLEMENTATION_VALUES = {"not_started", "in_progress", "implemented"}
RELEASE_VALUES = {"draft", "approved", "released"}
PHASE_VALUES = {"M0", "M1", "M2", "M3", "M4", "M5", "M6", "production"}

REQUIRED_ENUM_CHECKS = [
    ("ai_verdict", ("properties", "ai_verdict", "enum")),
    ("human_status", ("properties", "human_status", "enum")),
    ("review_jobs.status", ("properties", "status", "enum")),
    ("review_stages.stage", ("properties", "stage", "enum")),
    ("test_type", ("properties", "test_type", "enum")),
]

ISSUE_ENUM_CHECKS = [
    ("issues.status", ("properties", "status", "enum")),
    ("issues.severity", ("properties", "severity", "enum")),
    ("evidence_status", ("properties", "evidence_status", "enum")),
]


def _readme_links(lines: list[str]) -> list[tuple[int, str, str]]:
    pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    links: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        for match in pattern.finditer(line):
            target = match.group(2).strip()
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target = target.split("#", 1)[0]
            links.append((index + 1, match.group(1), target))
    return links


def check_doc_index(reporter: Reporter) -> None:
    reporter.checks_run += 1
    readme_lines = lib.read_lines(README)
    readme_text = "\n".join(readme_lines)
    for line_no, label, target in _readme_links(readme_lines):
        path = (lib.ROOT / target).resolve()
        if not path.exists():
            reporter.error(CHECK, rel(README), f"链接 {label}", f"目标不存在: {target}", line_no)

    for doc in sorted(lib.DOCS_DIR.glob("*.md")):
        if doc.name not in readme_text:
            reporter.error(CHECK, rel(README), "文档索引", f"缺少文档: docs/{doc.name}")

    for path in (
        lib.DESIGN_DIR / "decisions.yaml",
        lib.DESIGN_DIR / "verdict_cases.yaml",
        lib.DESIGN_DIR / "m0_acceptance.yaml",
        lib.DESIGN_DIR / "execution_plan.yaml",
        lib.DESIGN_DIR / "model_admission.yaml",
        lib.DESIGN_DIR / "experiment_protocol.yaml",
        lib.DESIGN_DIR / "kb_pilot.yaml",
        lib.DESIGN_DIR / "review_roster.yaml",
        SCRIPTS / "README.md",
    ):
        if rel(path) not in readme_text:
            reporter.error(CHECK, rel(README), "文档索引", f"缺少文件: {rel(path)}")


def check_doc_versions(reporter: Reporter) -> None:
    reporter.checks_run += 1
    state_match = re.search(r"\*\*状态\*\*：\*\*(?:design-)?v(\d+\.\d+)", lib.read_text(README))
    if not state_match:
        reporter.error(CHECK, rel(README), "状态", "README 状态行缺少 vX.Y 版本号")
        return
    repo_version = tuple(int(part) for part in state_match.group(1).split("."))
    for doc in sorted(lib.DOCS_DIR.glob("*.md")):
        match = re.search(r"版本：(v\d+\.\d+)", lib.read_text(doc))
        if not match:
            reporter.error(CHECK, rel(doc), "版本", "缺少 '> 版本：vX.Y' 头")
            continue
        version = tuple(int(part) for part in match.group(1)[1:].split("."))
        if version > repo_version:
            reporter.error(CHECK, rel(doc), "版本", f"{match.group(1)} 高于 README 状态 v{match.group(1)[1:]}")
        allowed = {"v1.0", "v1.1"} if doc.name.startswith("00-") else {"v1.3", "v1.4", "v1.5", "v1.6", "v1.7", "v1.8", "v1.9", "v1.10", "v1.11"}
        if match.group(1) not in allowed:
            reporter.error(CHECK, rel(doc), "版本", f"未知版本 {match.group(1)}（允许 {sorted(allowed)}）")


def _schema_enum(schema: dict[str, Any], path: tuple[str, ...], base: dict[str, Any] | None = None) -> set[Any]:
    node: Any = base if base is not None else schema
    for part in path:
        node = node[part]
    return {None if value == "null" else value for value in node}


def check_enums(reporter: Reporter) -> None:
    reporter.checks_run += 1
    dict_lines = lib.read_lines(DICT_DOC)
    schema = lib.load_json(SCHEMA, reporter, CHECK)

    for key, path in REQUIRED_ENUM_CHECKS:
        expected = lib.dictionary_enum(dict_lines, key)
        if expected is None:
            reporter.error(CHECK, rel(DICT_DOC), key, "字典中找不到该枚举")
            continue
        actual = _schema_enum(schema, path)
        if set(expected) != actual:
            reporter.error(
                CHECK,
                rel(SCHEMA),
                key,
                f"与 docs/17-全局数据字典.md 不一致：字典 {sorted(map(str, set(expected)))}，Schema {sorted(map(str, actual))}",
            )

    issue = schema["$defs"]["issue"]
    for key, path in ISSUE_ENUM_CHECKS:
        expected = lib.dictionary_enum(dict_lines, key)
        if expected is None:
            reporter.error(CHECK, rel(DICT_DOC), key, "字典中找不到该枚举")
            continue
        actual = _schema_enum(schema, path, issue)
        if key == "evidence_status":
            # docs/17 只列五个业务状态；Schema 额外允许 null 表示未判定
            actual = {value for value in actual if value is not None}
        if set(expected) != actual:
            reporter.error(
                CHECK,
                rel(SCHEMA),
                key,
                f"与 docs/17-全局数据字典.md 不一致：字典 {sorted(map(str, set(expected)))}，Schema {sorted(map(str, actual))}",
            )

    validity = lib.dictionary_enum(dict_lines, "issue_votes.validity")
    vote_validity = _schema_enum(schema, ("additionalProperties", "properties", "validity", "enum"), issue["properties"]["votes"])
    if validity is None or set(validity) != vote_validity:
        reporter.error(CHECK, rel(SCHEMA), "issue_votes.validity", "Schema 投票枚举与 docs/17 不一致")


def check_business_boundary(reporter: Reporter) -> None:
    """业务边界 BIZ-005：test_type 必须在 API/错误码/数据模型/报告中同源出现。"""
    reporter.checks_run += 1
    api = lib.read_text(API_DOC)
    data = lib.read_text(DATA_DOC)
    error_doc = lib.read_text(ERROR_DOC)
    for token, text, path in (
        ("case.test_type", api, API_DOC),
        ("UNSUPPORTED_TEST_TYPE", api, API_DOC),
        ("TEST_TYPE_REQUIRED", api, API_DOC),
        ("test_type", data, DATA_DOC),
        ("UNSUPPORTED_TEST_TYPE", error_doc, ERROR_DOC),
        ("TEST_TYPE_REQUIRED", error_doc, ERROR_DOC),
    ):
        if token not in text:
            reporter.error(CHECK, rel(path), "业务边界", f"缺少 {token}（docs/00 BIZ-005 / D172）")

    for path in (BIZ_DOC, API_DOC, DICT_DOC, DATA_DOC):
        for line_no, line in enumerate(lib.read_lines(path), start=1):
            if "默认 `functional`" in line and not any(word in line for word in ("废弃", "不再", "禁止")):
                reporter.error(
                    CHECK, rel(path), "test_type 默认值", "不得再把 functional 当作隐式默认；缺失必须 422 TEST_TYPE_REQUIRED", line_no
                )

    schema = lib.load_json(SCHEMA, reporter, CHECK)
    if "test_type" not in schema.get("properties", {}):
        reporter.error(CHECK, rel(SCHEMA), "test_type", "报告 Schema 缺少 test_type 字段")
    if "test_type_source" not in schema.get("properties", {}):
        reporter.error(CHECK, rel(SCHEMA), "test_type_source", "报告 Schema 缺少 test_type_source 字段")
    attachments = schema.get("properties", {}).get("attachments", {}).get("items", {})
    analyzed = attachments.get("properties", {}).get("analyzed_by_ai", {})
    if analyzed.get("const") is not False:
        reporter.error(CHECK, rel(SCHEMA), "attachments.analyzed_by_ai", "附件必须标注 analyzed_by_ai=false（v1 不做多模态）")

    completeness = schema.get("properties", {}).get("review_completeness", {}).get("properties", {})
    for field in ("full_participation", "stages_failed", "stages_pending"):
        if field not in completeness:
            reporter.error(CHECK, rel(SCHEMA), f"review_completeness.{field}", "缺少完整性语义字段（D171）")


def check_idempotency(reporter: Reporter) -> None:
    reporter.checks_run += 1
    texts = {name: lib.read_text(path) for name, path in (("03", API_DOC), ("01", ARCH_DOC), ("02", DATA_DOC))}
    formulas: dict[str, str] = {}
    for name, text in texts.items():
        match = re.search(r"idempotency_key\s*=\s*sha256\([^)]*\)", text, re.S)
        if not match:
            reporter.error(CHECK, rel(({"03": API_DOC, "01": ARCH_DOC, "02": DATA_DOC})[name]), "idempotency_key", "未找到幂等键公式")
            continue
        formulas[name] = lib.normalize_formula(match.group(0))
    if len(set(formulas.values())) > 1:
        reporter.error(
            CHECK,
            rel(API_DOC),
            "idempotency_key",
            f"01/02/03 公式不一致: { {name: value[:80] for name, value in formulas.items()} }",
        )

    api = texts["03"]
    for index in range(1, 8):
        if not re.search(rf"\|\s*S{index}\s*\|", api):
            reporter.error(CHECK, rel(API_DOC), f"S{index}", "缺少提交行为矩阵行")
    for token in ("202", "200", "422", "409", "REVIEW_IN_PROGRESS", "IDEMPOTENCY_KEY_CONFLICT"):
        if token not in api:
            reporter.error(CHECK, rel(API_DOC), "提交行为矩阵", f"缺少关键码 {token}")

    error_doc = lib.read_text(ERROR_DOC)
    if not re.search(r"\|\s*409\s*\|\s*`REVIEW_IN_PROGRESS`\s*\|", error_doc):
        reporter.error(CHECK, rel(ERROR_DOC), "REVIEW_IN_PROGRESS", "错误码表缺少 409 REVIEW_IN_PROGRESS")


def check_stale_semantics(reporter: Reporter) -> None:
    reporter.checks_run += 1
    paths = [README] + sorted(lib.DOCS_DIR.glob("*.md"))
    forbidden = [
        (re.compile(r"冲突返回已有报告或\s*409"), "旧的 409 幂等语义"),
        (re.compile(r"\|\s*409\s*\|\s*`?DUPLICATE`?\s*\|"), "已废弃的错误码 409 DUPLICATE"),
    ]
    for path in paths:
        lines = lib.read_lines(path)
        for index, line in enumerate(lines):
            # 清理记录/验收标准里会引用旧语义原文；带"废弃/不再/原描述"标记的行属于说明，不算残留
            if any(word in line for word in ("废弃", "不再", "原描述", "旧语义")):
                continue
            for pattern, reason in forbidden:
                if pattern.search(line):
                    reporter.error(CHECK, rel(path), "废弃语义", f"{reason}: {line.strip()[:80]}", index + 1)
            if "human_review_list" in line and not any(word in line for word in ("删除", "不再", "统一", "旧")):
                reporter.error(CHECK, rel(path), "human_review_list", "旧字段名，应统一为 human_review_items", index + 1)


def check_decisions(reporter: Reporter) -> None:
    reporter.checks_run += 1
    data = lib.load_yaml(DECISIONS, reporter, CHECK)
    if not isinstance(data, dict):
        reporter.error(CHECK, rel(DECISIONS), "root", "顶层必须是对象")
        return
    decisions = data.get("decisions", [])
    seen: set[str] = set()
    doc08_text = lib.read_text(DOCS08)
    doc08_ids = set(re.findall(r"\|\s*(D\d+)\s*\|", doc08_text))
    doc08_pd = set(re.findall(r"\|\s*(PD-\d{3})\s*\|", doc08_text))
    doc08_biz = set(re.findall(r"\|\s*(BIZ-\d{3})\s*\|", doc08_text))
    known = doc08_ids | doc08_pd | doc08_biz

    for index, decision in enumerate(decisions):
        did = decision.get("id")
        if not did:
            reporter.error(CHECK, rel(DECISIONS), f"decisions[{index}]", "缺少 id")
            continue
        if did in seen:
            reporter.error(CHECK, rel(DECISIONS), did, "决策 ID 重复")
        seen.add(did)
        if did not in known:
            reporter.error(CHECK, rel(DECISIONS), did, "docs/08 中不存在同一 ID 的决策（禁止同名不同义）")
        for field, allowed in (
            ("status", STATUS_VALUES),
            ("validation_status", VALIDATION_VALUES),
            ("implementation_status", IMPLEMENTATION_VALUES),
            ("release_status", RELEASE_VALUES),
            ("phase", PHASE_VALUES),
        ):
            value = decision.get(field)
            if value not in allowed:
                reporter.error(CHECK, rel(DECISIONS), f"{did}.{field}", f"非法状态 {value!r}（允许 {sorted(allowed)}）")
        for source in decision.get("source", []):
            if not _resolve_source(source):
                reporter.error(CHECK, rel(DECISIONS), f"{did}.source", f"引用目标不存在: {source}")

    for expected in (
        "D154", "D155", "D156", "D157", "D158", "D159", "D160", "D161", "D162", "D163", "D164",
        "D165", "D166", "D167", "D168",
        "D169", "D170", "D171", "D172", "D173", "D174", "D175", "D176", "D177", "D178", "D179", "D180",
        "D181", "D182", "D183", "D184", "D185", "D186", "D187", "D188", "D189", "D190", "D191", "D192",
        "D193", "D194", "D195", "D196", "D197", "D198", "D199", "D200", "D201", "D202",
        "D203", "D204", "D205", "D206", "D207", "D208",
        "D209", "D210", "D211", "D212", "D213", "D214",
        "D215", "D216", "D217", "D218",
    ):
        if expected not in known:
            reporter.error(CHECK, rel(DOCS08), expected, "docs/08 缺少 v1.4–v1.11 决策登记")
        if expected not in seen:
            reporter.error(CHECK, rel(DECISIONS), expected, "决策索引缺少 v1.4–v1.11 决策")

    # 业务基线：docs/00 §14、docs/08 §2.0.2、decisions.yaml 三处必须同集合
    biz_text = lib.read_text(BIZ_DOC)
    biz_ids = set(re.findall(r"\|\s*(BIZ-\d{3})\s*\|", biz_text))
    index_biz = {did for did in seen if did.startswith("BIZ-")}
    if len(biz_ids) != 15:
        reporter.error(CHECK, rel(BIZ_DOC), "§14", f"业务决策应为 15 条，实际 {len(biz_ids)} 条")
    if biz_ids != doc08_biz:
        reporter.error(
            CHECK,
            rel(DOCS08),
            "§2.0.2",
            f"BIZ 决策与 docs/00 §14 不一致：缺少 {sorted(biz_ids - doc08_biz)}，多出 {sorted(doc08_biz - biz_ids)}",
        )
    if biz_ids != index_biz:
        reporter.error(
            CHECK,
            rel(DECISIONS),
            "BIZ",
            f"BIZ 决策索引不完整：缺少 {sorted(biz_ids - index_biz)}，多出 {sorted(index_biz - biz_ids)}",
        )

    # phase 在 docs/00 §14、docs/08 §2.0.2、decisions.yaml 三处必须一致
    decision_phase = {str(item.get("id")): item.get("phase") for item in decisions}

    def _phase_map(text: str, start: str, end: str) -> dict[str, str]:
        start_index = text.find(start)
        if start_index < 0:
            return {}
        end_index = text.find(end, start_index)
        block = text[start_index : end_index if end_index > 0 else len(text)]
        result: dict[str, str] = {}
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) >= 4 and re.fullmatch(r"BIZ-\d{3}", cells[0]):
                result[cells[0]] = cells[3]
        return result

    biz_phase_doc = _phase_map(biz_text, "## 14. 当前业务决策基线", "## 15.")
    biz_phase_08 = _phase_map(doc08_text, "### 2.0.2 业务决策基线", "### 2.1")
    for did in sorted(biz_ids):
        expected = decision_phase.get(did)
        for source, mapping in ((rel(BIZ_DOC), biz_phase_doc), (rel(DOCS08), biz_phase_08)):
            actual = mapping.get(did)
            if actual and expected and actual != expected:
                reporter.error(CHECK, source, f"{did}.phase", f"期望 {expected!r}，实际 {actual!r}")

    # 文档中出现的 D 编号必须真实登记，避免"引用一个不存在的决策"
    referenced: set[str] = set()
    for path in [README] + sorted(lib.DOCS_DIR.glob("*.md")):
        referenced |= set(re.findall(r"(?<![A-Za-z0-9])D\d{1,3}(?![0-9])", lib.read_text(path)))
    for missing in sorted(referenced - known):
        reporter.error(CHECK, rel(DOCS08), missing, "文档引用了未登记的决策编号")

    # 待决事项与 docs/08 §2.16 同源（D180）
    open_questions = data.get("open_questions", [])
    q_ids: list[str] = []
    known_decision_ids = {str(item.get("id")) for item in decisions}
    for question in open_questions:
        qid = question.get("id")
        if not qid or not re.fullmatch(r"Q-\d{2}", qid):
            reporter.error(CHECK, rel(DECISIONS), str(qid), "待决事项 ID 必须形如 Q-01")
            continue
        q_ids.append(qid)
        if question.get("status") not in ("open", "resolved"):
            reporter.error(CHECK, rel(DECISIONS), f"{qid}.status", f"非法状态 {question.get('status')!r}")
        if question.get("phase") not in PHASE_VALUES:
            reporter.error(CHECK, rel(DECISIONS), f"{qid}.phase", f"非法阶段 {question.get('phase')!r}")
        if question.get("status") == "resolved" and question.get("resolution") not in known_decision_ids:
            reporter.error(CHECK, rel(DECISIONS), f"{qid}.resolution", "resolved 必须引用已登记决策 ID")
        for source in question.get("source", []):
            if not _resolve_source(source):
                reporter.error(CHECK, rel(DECISIONS), f"{qid}.source", f"引用目标不存在: {source}")
    if len(q_ids) != 18 or len(set(q_ids)) != 18:
        reporter.error(CHECK, rel(DECISIONS), "open_questions", f"应有 18 条且唯一，实际 {len(q_ids)} 条（唯一 {len(set(q_ids))}）")

    q_start = doc08_text.find("### 2.16 待决事项登记")
    q_end = doc08_text.find("### 2.17", q_start)
    doc_q = set(re.findall(r"\|\s*(Q-\d{2})\s*\|", doc08_text[q_start : q_end if q_end > 0 else len(doc08_text)]))
    if set(q_ids) != doc_q:
        reporter.error(
            CHECK,
            rel(DOCS08),
            "§2.16",
            f"与 decisions.yaml 不一致：缺少 {sorted(set(q_ids) - doc_q)}，多出 {sorted(doc_q - set(q_ids))}",
        )

    distribution: dict[str, list[str]] = {}
    for decision in decisions:
        distribution.setdefault(str(decision.get("phase")), []).append(str(decision.get("id")))
    reporter.note(
        "决策阶段分布: "
        + "；".join(f"{phase}={len(ids)}（{','.join(ids)}）" for phase, ids in sorted(distribution.items()))
    )


def _resolve_source(source: str) -> bool:
    if source == "README":
        return README.exists()
    candidate = lib.ROOT / source
    if candidate.exists():
        return True
    if re.fullmatch(r"docs/\d{2}", source):
        return any(lib.DOCS_DIR.glob(f"{source.split('/')[1]}-*.md"))
    if source in ("schemas/README", "rubric/README"):
        return (lib.ROOT / f"{source}.md").exists()
    return False


def check_readme_decisions(reporter: Reporter) -> None:
    reporter.checks_run += 1
    lines = lib.read_lines(README)
    in_section = False
    numbers: list[int] = []
    for line in lines:
        if line.startswith("## 2. 共识决策记录"):
            in_section = True
            continue
        if in_section and line.startswith("## 3."):
            break
        if not in_section or not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[0].isdigit():
            continue
        numbers.append(int(cells[0]))
    if not numbers:
        reporter.error(CHECK, rel(README), "决策表", "未解析到任何决策行")
        return
    if len(numbers) != len(set(numbers)):
        reporter.error(CHECK, rel(README), "决策表", f"决策编号重复: {sorted({n for n in numbers if numbers.count(n) > 1})}")
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        missing = sorted(set(expected) - set(numbers))
        reporter.error(CHECK, rel(README), "决策表", f"编号不连续，缺少 {missing}")


def check_doc_paths(reporter: Reporter) -> None:
    reporter.checks_run += 1
    pattern = re.compile(r"docs/\d{2}-[A-Za-z0-9\u4e00-\u9fff\-]+\.md")
    for doc in sorted(lib.DOCS_DIR.glob("*.md")) + [README]:
        text = lib.read_text(doc)
        for match in pattern.finditer(text):
            relative = match.group(0).rstrip(".")
            if not (lib.ROOT / relative).exists():
                reporter.error(CHECK, rel(doc), "文档引用", f"目标不存在: {relative}")


def check_error_codes(reporter: Reporter) -> None:
    reporter.checks_run += 1
    api_lines = lib.read_lines(API_DOC)
    error_lines = lib.read_lines(ERROR_DOC)

    start = next((index for index, line in enumerate(api_lines) if line.startswith("## 8. 错误码")), None)
    if start is None:
        reporter.error(CHECK, rel(API_DOC), "§8 错误码", "未找到错误码章节")
        return
    api_codes: dict[str, int] = {}
    for index in range(start, len(api_lines)):
        line = api_lines[index].strip()
        if index > start and line.startswith("## "):
            break
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        match = re.fullmatch(r"`([A-Z_]+)`", cells[1])
        if match:
            api_codes[match.group(1)] = index + 1

    error_codes: dict[str, int] = {}
    for index, line in enumerate(error_lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 4:
            continue
        match = re.fullmatch(r"`([A-Z_]+)`", cells[1])
        if match:
            error_codes[match.group(1)] = index + 1
            if not cells[3]:
                reporter.error(CHECK, rel(ERROR_DOC), match.group(1), "缺少 retryable 列", index + 1)

    if not error_codes:
        reporter.error(CHECK, rel(ERROR_DOC), "错误码表", "未解析到任何错误码")
        return
    for code, line_no in api_codes.items():
        if code not in error_codes:
            reporter.error(CHECK, rel(API_DOC), code, "错误码未在 docs/19 中定义（以 19 为唯一规范）", line_no)
    if "DUPLICATE" in error_codes:
        reporter.error(CHECK, rel(ERROR_DOC), "DUPLICATE", "已废弃的错误码仍在定义表中", error_codes["DUPLICATE"])


def check_ci_workflow(reporter: Reporter) -> None:
    reporter.checks_run += 1
    workflow = lib.ROOT / ".github" / "workflows" / "contracts.yml"
    if not workflow.exists():
        reporter.error(CHECK, rel(workflow), "file", "缺少契约检查 CI 工作流")
        return
    text = lib.read_text(workflow)
    for token in ("scripts/check_contracts.py", "pytest tests/contract"):
        if token not in text:
            reporter.error(CHECK, rel(workflow), "CI 步骤", f"工作流缺少步骤: {token}")


def check_schema_version(reporter: Reporter) -> None:
    reporter.checks_run += 1
    if not SCHEMA_FROZEN.exists():
        reporter.error(CHECK, rel(SCHEMA_FROZEN), "file", "缺少 report-1.0 冻结副本")
        return
    if lib.read_text(SCHEMA) != lib.read_text(SCHEMA_FROZEN):
        reporter.error(CHECK, rel(SCHEMA_FROZEN), "freeze", "当前 Schema 与冻结副本不一致")
    schema = lib.load_json(SCHEMA, reporter, CHECK)
    try:
        import jsonschema

        jsonschema.Draft202012Validator.check_schema(schema)
    except ImportError:
        reporter.error(CHECK, rel(SCHEMA), "dependency", "缺少 jsonschema，无法校验报告 Schema 自身合法性")
    except jsonschema.exceptions.SchemaError as exc:  # type: ignore[name-defined]
        reporter.error(CHECK, rel(SCHEMA), "schema", f"自身不是合法 JSON Schema: {exc.message}")
    required = set(schema.get("required", []))
    for field in ("report_schema_version", "issues", "versions"):
        if field not in required:
            reporter.error(CHECK, rel(SCHEMA), "required", f"报告 Schema 必填字段缺少 {field}")
    readme = lib.read_text(lib.SCHEMAS_DIR / "README.md")
    if "report-1.0" not in readme:
        reporter.error(CHECK, rel(lib.SCHEMAS_DIR / "README.md"), "版本表", "缺少 report-1.0 版本记录")


def check_scripts_index(reporter: Reporter) -> None:
    reporter.checks_run += 1
    readme = SCRIPTS / "README.md"
    if not readme.exists():
        reporter.error(CHECK, rel(readme), "file", "缺少 scripts/README.md")
        return
    text = lib.read_text(readme)
    for script in sorted(SCRIPTS.glob("*.py")):
        if script.name not in text:
            reporter.error(CHECK, rel(readme), "脚本索引", f"缺少脚本说明: {script.name}")


def run(reporter: Reporter) -> None:
    check_doc_index(reporter)
    check_doc_versions(reporter)
    check_enums(reporter)
    check_business_boundary(reporter)
    check_idempotency(reporter)
    check_stale_semantics(reporter)
    check_decisions(reporter)
    check_readme_decisions(reporter)
    check_doc_paths(reporter)
    check_error_codes(reporter)
    check_ci_workflow(reporter)
    check_schema_version(reporter)
    check_scripts_index(reporter)


def main() -> int:
    reporter = Reporter()
    run(reporter)
    return lib.print_report(reporter, title="跨文档契约检查", verbose=True)


if __name__ == "__main__":
    raise SystemExit(main())
