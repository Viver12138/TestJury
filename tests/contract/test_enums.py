"""ACC-M0-005：Python Enum 与 docs/17 全局数据字典同源。

本测试直接解析 `docs/17-全局数据字典.md` 的表格，逐项与 `app.core.enums` 比对；
新增/删除枚举值而未同步字典（或反之）都会失败，禁止手工复制同步。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core import enums

REPO_ROOT = Path(__file__).resolve().parents[2]
DICT_PATH = REPO_ROOT / "docs" / "17-全局数据字典.md"

ENUM_TO_KEY: dict[type, str] = {
    enums.ReviewStatus: "review_jobs.status",
    enums.TestType: "test_type",
    enums.BatchStatus: "batches.status",
    enums.AiVerdict: "ai_verdict",
    enums.HumanStatus: "human_status",
    enums.DecisionValue: "review_decisions.decision",
    enums.Stage: "review_stages.stage",
    enums.StageStatus: "review_stages.status",
    enums.DegradedReason: "degraded_reasons",
    enums.CandidateStatus: "review_candidates.status",
    enums.VoteValidity: "issue_votes.validity",
    enums.Severity: "issues.severity",
    enums.IssueStatus: "issues.status",
    enums.ChiefDecision: "issues.chief_decision",
    enums.VoteCompleteness: "vote_completeness",
    enums.EvidenceType: "evidence_type",
    enums.EvidenceLevel: "evidence_level",
    enums.EvidenceStrength: "evidence_strength",
    enums.EvidenceStatus: "evidence_status",
    enums.ClaimRole: "claim_role",
    enums.ClaimRelation: "claim_relation",
    enums.RuleStatus: "rule_status",
    enums.KbVersionStatus: "kb_versions.status",
    enums.OriginType: "origin_type",
    enums.VerificationStatus: "verification_status",
    enums.ActorType: "actor_type",
    enums.Topology: "topology",
    enums.ReviewTaskStatus: "human_review_tasks.status",
    enums.ReviewLevel: "human_review_tasks.review_level",
    enums.ParticipantStatus: "review_participants.status",
    enums.GapResolution: "kb_gaps.gap_resolution",
}


def _lines() -> list[str]:
    return DICT_PATH.read_text(encoding="utf-8").splitlines()


def _table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _extract_values(key: str, *, startswith: bool = False) -> set[str]:
    """从字典表格中取出枚举取值列（第一个单元格匹配 key 的行）。"""

    for line in _lines():
        cells = _table_cells(line)
        if len(cells) < 2:
            continue
        match = re.fullmatch(r"`([^`]+)`(?:（[^）]*）)?", cells[0])
        if not match:
            continue
        cell_key = match.group(1)
        hit = cell_key == key or (startswith and cell_key.startswith(key))
        if not hit:
            continue
        values = set()
        for raw in re.findall(r"`([^`]+)`", cells[1]):
            value = raw.strip().strip('"')
            if value in ("null", ""):
                continue
            values.add(value)
        if values:
            return values
    raise AssertionError(f"docs/17 中找不到枚举行: {key}")


@pytest.mark.parametrize("enum_cls,key", list(ENUM_TO_KEY.items()), ids=lambda value: getattr(value, "__name__", value))
def test_enum_matches_dictionary(enum_cls: type, key: str) -> None:
    documented = _extract_values(key)
    actual = {item.value for item in enum_cls}
    assert actual == documented, (
        f"{enum_cls.__name__} 与 docs/17 `{key}` 不一致："
        f"文档多 {sorted(documented - actual)}，代码多 {sorted(actual - documented)}"
    )


def test_issue_votes_severity_matches_dictionary() -> None:
    documented = _extract_values("issue_votes.severity")
    actual = {item.value for item in enums.Severity}
    assert actual == documented


def test_claim_status_and_doc_type_are_documented() -> None:
    lines = _lines()

    claim_row = next(line for line in lines if line.startswith("| claim 级状态"))
    claim_values = {
        value.strip('"') for value in re.findall(r"`([^`]+)`", claim_row.split("|")[2])
    }
    assert claim_values == {item.value for item in enums.ClaimStatus}

    # doc_type 表格的取值在第一列
    start = next(index for index, line in enumerate(lines) if line.startswith("## 4. 知识库"))
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("### 4.1") or line.startswith("> 02 之前"):
            break
        cells = _table_cells(line)
        if len(cells) >= 2 and re.fullmatch(r"`[a-z_]+`", cells[0]):
            block.append(cells[0].strip("`"))
    assert set(block) == {item.value for item in enums.DocType}


def test_role_table_matches_dictionary() -> None:
    lines = _lines()
    start = next(index for index, line in enumerate(lines) if line.startswith("## 5. 角色与权限"))
    roles: set[str] = set()
    for line in lines[start + 1 :]:
        if line.startswith("### 5.1"):
            break
        cells = _table_cells(line)
        if len(cells) >= 2 and re.fullmatch(r"`[a-z_]+`", cells[0]):
            roles.add(cells[0].strip("`"))
    assert roles == {item.value for item in enums.Role}
