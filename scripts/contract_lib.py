"""契约检查共享工具：路径、读取、发现项与统一输出。

输出约定（docs/28 §3.3）：每条失败必须包含
  [检查项] 文件:行 规则/字段 期望 vs 实际
这样 CI 日志可以直接定位到需要修改的位置，而不是只报"检查失败"。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

# TJ_REPO_ROOT 允许契约检查在临时副本上运行（用于变异测试，见 M0-08 ACC-M0-017）。
ROOT = Path(os.environ.get("TJ_REPO_ROOT") or Path(__file__).resolve().parent.parent).resolve()

DOCS_DIR = ROOT / "docs"
SCHEMAS_DIR = ROOT / "schemas"
RUBRIC_DIR = ROOT / "rubric"
DESIGN_DIR = ROOT / "design"


@dataclass
class Finding:
    check: str
    file: str
    line: int | None
    item: str
    message: str
    severity: str = "error"

    def render(self) -> str:
        location = f"{self.file}:{self.line}" if self.line else self.file
        return f"[{self.severity.upper()}] {self.check} | {location} | {self.item} | {self.message}"


@dataclass
class Reporter:
    findings: list[Finding] = field(default_factory=list)
    checks_run: int = 0
    notes: list[str] = field(default_factory=list)

    def error(self, check: str, file: str | Path, item: str, message: str, line: int | None = None) -> None:
        self.findings.append(Finding(check, str(file), line, item, message, "error"))

    def warn(self, check: str, file: str | Path, item: str, message: str, line: int | None = None) -> None:
        self.findings.append(Finding(check, str(file), line, item, message, "warn"))

    def note(self, message: str) -> None:
        self.notes.append(message)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warn"]

    def ok(self) -> bool:
        return not self.errors


def rel(path: Path) -> str:
    """仓库相对路径（用于输出，避免暴露本机绝对路径）。"""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_lines(path: Path) -> list[str]:
    return read_text(path).splitlines()


def load_yaml(path: Path, reporter: Reporter | None = None, check: str = "parse") -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        if reporter is not None:
            reporter.error(check, rel(path), "YAML", f"解析失败: {exc}")
        raise
    except OSError as exc:
        if reporter is not None:
            reporter.error(check, rel(path), "file", f"读取失败: {exc}")
        raise


def load_json(path: Path, reporter: Reporter | None = None, check: str = "parse") -> Any:
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        if reporter is not None:
            reporter.error(check, rel(path), "JSON", f"解析失败: {exc}")
        raise


def find_line(lines: list[str], pattern: str, start: int = 0) -> int | None:
    """返回第一个匹配的 1-based 行号。"""
    regex = re.compile(pattern)
    for index in range(start, len(lines)):
        if regex.search(lines[index]):
            return index + 1
    return None


def md_table_rows(lines: list[str], header_contains: str) -> list[tuple[int, list[str]]]:
    """解析 Markdown 表格：返回 (行号, 单元格列表)，跳过表头与分隔行。"""
    rows: list[tuple[int, list[str]]] = []
    in_table = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            in_table = False
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not in_table:
            if header_contains in stripped:
                in_table = True
            continue
        if all(set(cell) <= set("-: ") for cell in cells):
            continue
        rows.append((index + 1, cells))
    return rows


def dictionary_enum(lines: list[str], key: str) -> list[Any] | None:
    """从 docs/17 的 Markdown 表格读取某个枚举的取值列表。

    行形如 `| `ai_verdict` | `blocked` / `conditional` / ... | 说明 |`。
    返回去掉反引号后的值（`null` 转为 None）；找不到返回 None。
    """
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        first = cells[0].strip("` ")
        if first != key:
            continue
        values = re.findall(r"`([^`]+)`", cells[1])
        if not values:
            return None
        return [None if value == "null" else value for value in values]
    return None


def unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def normalize_formula(text: str) -> str:
    """把幂等键公式块规范化为空白压缩后的字符串，用于跨文件一致性比较。"""
    return re.sub(r"\s+", " ", text).strip()


def extract_fenced_block(text: str, keyword: str) -> str | None:
    """提取包含 keyword 的第一个 ``` 代码块内容。"""
    for match in re.finditer(r"```[a-zA-Z]*\n(.*?)```", text, re.DOTALL):
        block = match.group(1)
        if keyword in block:
            return block
    return None


def print_report(reporter: Reporter, *, title: str, verbose: bool = False) -> int:
    print(f"== {title} ==")
    for note in reporter.notes:
        print(f"[NOTE] {note}")
    for finding in reporter.findings:
        if finding.severity == "warn" and not verbose:
            print(finding.render())
        elif finding.severity == "error":
            print(finding.render())
    errors = len(reporter.errors)
    warnings = len(reporter.warnings)
    if errors:
        print(f"\n结果: 失败（{errors} 个错误，{warnings} 个警告）")
        return 1
    print(f"\n结果: 通过（{reporter.checks_run} 项检查，{warnings} 个警告）")
    return 0


def require(condition: bool, reporter: Reporter, check: str, file: str | Path, item: str, message: str, line: int | None = None) -> bool:
    if not condition:
        reporter.error(check, file, item, message, line)
    return condition
