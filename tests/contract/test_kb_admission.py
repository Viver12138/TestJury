"""Mutation checks for knowledge boundaries that must never silently grant admission."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from app.knowledge.audit import audit_repository, repo_path, source_ref
from app.knowledge.build import build_candidate, evidence_for_ref, sections
from app.knowledge.contract import (
    KnowledgeDocument,
    KnowledgeError,
    load_yaml,
    load_yaml_text,
    normalize_metadata,
    read_document,
    validate_baseline,
)

ROOT = Path(__file__).resolve().parents[2]


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _metadata():
    contract = load_yaml(ROOT / "design/kb_contract.yaml")
    document = read_document(
        ROOT / "kb_content/minishop/rules/order/RULE-ORDER-003.md",
        contract,
        project_id="minishop",
        modules={"order"},
    )
    return contract, copy.deepcopy(document.metadata)


@pytest.mark.parametrize("text", ["a: 1\na: 2", "outer:\n  a: 1\n  a: 2", "base: &base {a: 1}\nmerged: {<<: *base, a: 2}"])
def test_duplicate_yaml_keys_are_errors(text):
    with pytest.raises(KnowledgeError, match="duplicate YAML key"):
        load_yaml_text(text)


def test_approved_maps_to_reviewed_without_upgrading_evidence():
    contract, metadata = _metadata()
    canonical = normalize_metadata(metadata, contract, project_id="minishop", modules={"order"})
    assert canonical["rule_status"] == "reviewed"
    assert canonical["doc_id"] == metadata["id"]
    assert canonical["evidence_level"] == "E2"
    metadata["knowledge_type"] = "EXPERT_KNOWLEDGE"
    metadata["evidence_level"] = "E4"
    canonical = normalize_metadata(metadata, contract, project_id="minishop", modules={"order"})
    assert canonical["doc_type"] == "design"
    assert canonical["evidence_level"] == "E4"


@pytest.mark.parametrize(
    "field,value",
    [
        ("module_id", "backpack"),
        ("project_id", "another_project"),
        ("doc_id", "a_different_id"),
        ("status", "published"),
        ("reviewer", None),
        ("rule_status", "published"),
    ],
)
def test_metadata_cannot_bypass_scope_or_review(field, value):
    contract, metadata = _metadata()
    metadata[field] = value
    with pytest.raises(KnowledgeError):
        normalize_metadata(metadata, contract, project_id="minishop", modules={"order"})


def test_branch_name_and_implicit_baseline_are_rejected():
    contract = load_yaml(ROOT / "design/kb_contract.yaml")
    with pytest.raises(KnowledgeError, match="explicit"):
        validate_baseline(None, contract)
    with pytest.raises(KnowledgeError, match="immutable"):
        validate_baseline(
            {
                "type": "current_implementation",
                "product_version": "1.0.0",
                "source_ref": "repository",
                "source_version": "main",
            },
            contract,
        )


def test_clean_candidate_is_valid_but_not_publishable():
    result = audit_repository(ROOT)
    assert not result.errors, result.errors
    assert len(result.documents) == 37
    assert result.payload()["content_statuses"] == {"approved": 37}
    assert not result.payload()["release_ready"]
    assert "publication:not_completed" in result.release_blockers
    assert result.snapshot_verified
    assert result.manual_review_verified
    assert result.source_counts == {"matched": 78, "changed": 1, "missing": 1}
    assert "source_snapshot:data/minishop.db:missing" not in result.release_blockers


def test_original_snapshot_bytes_cannot_be_tampered_with(workdir, repo_copy):
    root = repo_copy(workdir / "archive")
    binding = load_yaml(root / "kb_content/_delivery/source_binding.yaml")
    path = root / binding["snapshot_archive"]["path"]
    path.write_bytes(path.read_bytes() + b"tampered")
    result = audit_repository(root)
    assert any("snapshot archive SHA-256 mismatch" in error for error in result.errors)


def test_original_workbook_cannot_change_after_transcript_verification(workdir, repo_copy):
    root = repo_copy(workdir / "workbook")
    binding = load_yaml(root / "kb_content/_delivery/source_binding.yaml")
    path = root / binding["manual_decisions"]["original_workbook"]["path"]
    path.write_bytes(path.read_bytes() + b"tampered")
    result = audit_repository(root)
    assert any("original workbook" in error for error in result.errors)


@pytest.mark.parametrize("path", ["data/minishop.db", ".gitignore"])
def test_snapshot_only_content_is_not_attributed_to_a_git_commit(path):
    binding = load_yaml(ROOT / "kb_content/_delivery/source_binding.yaml")
    evidence = evidence_for_ref("Minishop/" + path, binding)
    assert evidence["content_commit"] is None
    assert evidence["snapshot_archive"]
    assert evidence["snapshot_sha256"]


def test_approved_body_edit_requires_reapproval(workdir, repo_copy):
    root = repo_copy(workdir / "body")
    path = root / "kb_content/minishop/rules/order/RULE-ORDER-003.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n新增强制规则。\n", encoding="utf-8")
    result = audit_repository(root)
    assert any("approved content changed" in error for error in result.errors)


def test_unreviewed_document_cannot_be_promoted_by_changing_status(workdir, repo_copy):
    root = repo_copy(workdir / "approval")
    path = root / "kb_content/minishop/rules/order/RULE-ORDER-008.md"
    text = path.read_text(encoding="utf-8").replace("status: in_review", "status: approved")
    text = text.replace("changes_applied_pending_reapproval", "approved_after_review")
    text += "\n未经复核新增：所有订单无需支付即可发货。\n"
    path.write_text(text, encoding="utf-8")
    result = audit_repository(root)
    assert any("review lock" in error for error in result.errors)


def test_verification_requires_evidence_and_finished_implementation(workdir, repo_copy):
    root = repo_copy(workdir / "verification")
    path = root / "kb_content/minishop/_governance/conflicts.yaml"
    data = load_yaml(path)
    target = next(item for item in data["conflicts"] if item["id"] == "CONFLICT-010")
    target["verification_status"] = "passed"
    _write_yaml(path, data)
    result = audit_repository(root)
    assert any("passed verification requires" in error for error in result.errors)


def test_source_binding_cannot_relabel_changed_data_as_a_match(workdir, repo_copy):
    root = repo_copy(workdir / "binding")
    path = root / "kb_content/_delivery/source_binding.yaml"
    data = load_yaml(path)
    data["files"][0]["state"] = "matched"
    _write_yaml(path, data)
    result = audit_repository(root)
    assert any("matched source must have identical hashes" in error for error in result.errors)


def test_ledger_cannot_silently_reverse_a_human_decision(workdir, repo_copy):
    root = repo_copy(workdir / "decision")
    path = root / "kb_content/minishop/_governance/pending_confirmation.yaml"
    data = load_yaml(path)
    target = next(item for item in data["items"] if item["id"] == "Q-04")
    target["decision_note"] = "Refund rejection always returns PAID."
    _write_yaml(path, data)
    result = audit_repository(root)
    assert any("decision differs from controlled review transcript" in error for error in result.errors)


def test_source_line_bounds_are_checked_without_a_checkout(workdir, repo_copy):
    root = repo_copy(workdir / "line_bounds")
    path = root / "kb_content/minishop/rules/order/RULE-ORDER-008.md"
    text = path.read_text(encoding="utf-8").replace("#L39-L118", "#L39-L99999")
    path.write_text(text, encoding="utf-8")
    result = audit_repository(root)
    assert any("exceeds snapshot lines" in error for error in result.errors)


@pytest.mark.parametrize("value", ["../outside", "C:/Users/private", "/absolute", "a/../../outside", "a\\b"])
def test_authored_paths_cannot_escape_repository(value):
    with pytest.raises(KnowledgeError):
        repo_path(ROOT, value)


def test_source_locator_rejects_inverted_range():
    with pytest.raises(KnowledgeError, match="inverted"):
        source_ref("Minishop/backend/main.py#L50-L2")


def test_sections_preserve_tables_and_headings_inside_code():
    body = "# First\n| a | b |\n|---|---|\n| 1 | 2 |\n```md\n# inside code\n```\n# Second\nText\n"
    document = KnowledgeDocument(Path("example.md"), {"knowledge_type": "INTERFACE", "title": "Example"}, body, {})
    parsed = sections(document)
    assert len(parsed) == 2
    assert "| 1 | 2 |" in parsed[0][1]
    assert "# inside code" in parsed[0][1]
    rule = KnowledgeDocument(Path("rule.md"), {"knowledge_type": "BUSINESS_RULE", "title": "Rule"}, body, {})
    assert sections(rule) == [("Rule", body)]


def test_unclosed_code_fence_blocks_candidate_parsing():
    document = KnowledgeDocument(
        Path("example.md"), {"knowledge_type": "INTERFACE", "title": "Example"}, "```py\nx = 1\n", {}
    )
    with pytest.raises(KnowledgeError, match="unclosed"):
        sections(document)


def test_capability_flags_cannot_activate_unpublished_content(workdir, repo_copy):
    root = repo_copy(workdir / "capability")
    path = root / "kb_content/minishop/_governance/admission.yaml"
    data = load_yaml(path)
    data["capabilities"][0]["formal_admission"] = "allowed"
    _write_yaml(path, data)
    result = audit_repository(root)
    assert any("cannot grant formal admission" in error for error in result.errors)


def test_admission_scope_changes_produce_a_new_build_version(workdir, repo_copy):
    root = repo_copy(workdir / "scope_version")
    before = build_candidate(root, baseline_type="current_implementation")
    path = root / "kb_content/minishop/_governance/admission.yaml"
    data = load_yaml(path)
    data["capabilities"][0]["restrictions"] += "; API smoke checks only."
    _write_yaml(path, data)
    after = build_candidate(root, baseline_type="current_implementation")
    assert before["kb_content_version"] == after["kb_content_version"]
    assert before["kb_build_version"] != after["kb_build_version"]


def test_release_command_fails_even_when_integrity_passes():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_kb.py"), "--release", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True, payload
    assert payload["release_ready"] is False
    assert completed.returncode == 1
