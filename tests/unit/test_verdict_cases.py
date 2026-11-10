"""ACC-M0-011：Verdict 真值表全部用例通过，且结论只由 verdict.py 产生。

用例来自 `design/verdict_cases.yaml`（36 条），由 `scripts/verdict_reference.py`
作为规范参考；生产实现必须逐条一致（docs/12 §9）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from app.pipeline.verdict import VerdictInputError, compute_verdict

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES = yaml.safe_load((REPO_ROOT / "design" / "verdict_cases.yaml").read_text("utf-8"))["cases"]
COMPARED_KEYS = (
    "ai_verdict",
    "issue_statuses",
    "human_review_required",
    "review_completeness",
    "arbitration_required",
)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_verdict_cases(case: dict) -> None:
    expected = case["expected"]
    if expected.get("error") is True:
        with pytest.raises(VerdictInputError):
            compute_verdict(case["input"])
        return

    result = compute_verdict(case["input"]).to_dict()
    for key in COMPARED_KEYS:
        if key in expected:
            assert result[key] == expected[key], f"{case['id']} ({case['rule']}) {key} 不一致"


def test_ai_verdict_is_only_computed_in_verdict_module() -> None:
    """禁止其他模块自行拼 ai_verdict 常量（docs/06 §3.1）。"""

    pattern = re.compile(r"AiVerdict\.(BLOCKED|CONDITIONAL|NEED_HUMAN)")
    offenders: list[str] = []
    for path in (REPO_ROOT / "app").rglob("*.py"):
        if path.name == "verdict.py" or path.name == "enums.py":
            continue
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"ai_verdict 只能由 app/pipeline/verdict.py 产生，违规文件: {offenders}"


def test_all_cases_are_covered() -> None:
    assert len(CASES) == 36
    kinds = {case["kind"] for case in CASES}
    assert {"positive", "negative", "boundary", "invalid"} <= kinds
