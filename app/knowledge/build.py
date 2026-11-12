"""Deterministic, offline candidate parsing; output is never an active runtime index."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.knowledge.audit import audit_repository, source_ref
from app.knowledge.contract import KnowledgeDocument, KnowledgeError, load_yaml, validate_baseline

PARSER_VERSION = "markdown-sections-2"


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def sections(document: KnowledgeDocument) -> list[tuple[str, str]]:
    """Preserve complete rules/flows, fenced blocks and Markdown table rows."""
    atomic = document.metadata["knowledge_type"] in {"BUSINESS_RULE", "WORKFLOW"}
    result: list[tuple[str, str]] = []
    heading = document.metadata["title"]
    lines: list[str] = []
    fence: tuple[str, int] | None = None
    # Historical signoffs can describe superseded text; they are provenance, not current rules.
    body = document.body.split("\n---\n\n## 复核记录", 1)[0]
    for line in body.splitlines(keepends=True):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            value = marker[1]
            if fence is None:
                fence = (value[0], len(value))
            elif value[0] == fence[0] and len(value) >= fence[1] and not line[marker.end() :].strip():
                fence = None
        if not atomic and fence is None and re.match(r"^#\s+", line):
            if "".join(lines).strip():
                result.append((heading, "".join(lines)))
            heading = line.lstrip("#").strip()
            lines = []
        lines.append(line)
    if fence:
        raise KnowledgeError(f"{document.metadata.get('id', document.path)}: unclosed Markdown code fence")
    if "".join(lines).strip():
        result.append((heading, "".join(lines)))
    return result


def evidence_for_ref(ref: str, binding: dict[str, Any]) -> dict[str, Any]:
    """A snapshot-only file must never acquire a fictional Git content commit."""
    if not ref.strip().startswith("Minishop/"):
        path = ref.strip().split("#", 1)[0]
        return {"source_ref": ref.strip(), "internal_path": path, "sha256": binding["internal_sources"][path]}
    path, _, _ = source_ref(ref)
    item = next(item for item in binding["files"] if item["path"] == path)
    archive = binding.get("snapshot_archive", {})
    return {
        "source_ref": ref.strip(),
        "snapshot_sha256": item["snapshot_sha256"],
        "repository": binding["repository"],
        "repository_path": path,
        "content_commit": binding["commit"] if item["state"] == "matched" else None,
        "git_comparison": item["state"],
        "snapshot_archive": archive.get("path"),
        "snapshot_archive_sha256": archive.get("sha256"),
        "snapshot_member": f"Minishop/{path}",
    }


def build_candidate(root: Path, *, baseline_type: str, source_root: Path | None = None) -> dict[str, Any]:
    audit = audit_repository(root, source_root=source_root)
    if audit.errors or not audit.sources_verified:
        raise KnowledgeError("candidate build requires successful source verification: " + "; ".join(audit.errors))
    contract = load_yaml(root / "design/kb_contract.yaml")
    policy = load_yaml(root / "kb_content/minishop/project/review_policy.yaml")
    baseline = validate_baseline(policy["baselines"].get(baseline_type), contract)
    binding = load_yaml(root / "kb_content/_delivery/source_binding.yaml")
    sources = {item["path"]: item for item in binding["files"]}
    eligible: list[KnowledgeDocument] = []
    excluded = []
    for document in audit.documents:
        reasons = []
        if document.metadata["status"] != "approved":
            reasons.append("pending_review")
        for ref in document.metadata["source_ref"].split(";"):
            if ref.strip().startswith("Minishop/"):
                path, _, _ = source_ref(ref)
                if sources[path]["state"] != "matched" and not audit.snapshot_verified:
                    reasons.append(f"source_not_reproducible:{path}")
        if baseline["product_version"] not in document.canonical["product_version"]:
            reasons.append("product_version_mismatch")
        if reasons:
            excluded.append({"doc_id": document.metadata["id"], "reasons": reasons})
        else:
            eligible.append(document)
    content_version = "kb-" + _digest({d.metadata["id"]: d.digest for d in audit.documents})
    implementation = Path(__file__).parent
    parser_fingerprint = _digest(
        {name: (implementation / name).read_text(encoding="utf-8") for name in ("contract.py", "audit.py", "build.py")}
    )
    governance = root / "kb_content/minishop/_governance"
    governance_fingerprint = _digest(
        {
            name: load_yaml(governance / name)
            for name in (
                "conflicts.yaml",
                "pending_confirmation.yaml",
                "knowledge_gaps.yaml",
                "admission.yaml",
                "review_lock.yaml",
            )
        }
    )
    build_version = "kb-build-" + _digest(
        {
            "content": content_version,
            "parser": PARSER_VERSION,
            "parser_fingerprint": parser_fingerprint,
            "governance_fingerprint": governance_fingerprint,
            "contract": contract,
            "baseline": baseline,
            "source_binding": binding,
        }
    )
    chunks = []
    for document in eligible:
        for index, (heading, text) in enumerate(sections(document)):
            chunks.append(
                {
                    "chunk_id": _digest(["minishop", document.metadata["id"], index, build_version]),
                    "project_id": "minishop",
                    "doc_id": document.metadata["id"],
                    "module": document.canonical["module"],
                    "doc_type": document.canonical["doc_type"],
                    "knowledge_type": document.metadata["knowledge_type"],
                    "rule_status": "reviewed",
                    "evidence_level": document.metadata["evidence_level"],
                    "product_version": document.canonical["product_version"],
                    "platforms": document.metadata["platforms"],
                    "effective_from": (
                        str(document.metadata["effective_from"]) if document.metadata["effective_from"] else None
                    ),
                    "effective_until": (
                        str(document.metadata["effective_until"]) if document.metadata["effective_until"] else None
                    ),
                    "source_ref": document.metadata["source_ref"],
                    "source_version": document.metadata["source_version"],
                    "source_repository": binding["repository"],
                    "implementation_commit": binding["commit"],
                    "source_evidence": [
                        evidence_for_ref(ref, binding) for ref in document.metadata["source_ref"].split(";")
                    ],
                    "heading_path": heading,
                    "chunk_index": index,
                    "content_hash": hashlib.sha256(text.encode()).hexdigest(),
                    "text": text,
                    "kb_content_version": content_version,
                    "kb_build_version": build_version,
                }
            )
    return {
        "status": "candidate",
        "publication_status": "unpublished",
        "formal_admission": "blocked",
        "project_id": "minishop",
        "kb_content_version": content_version,
        "kb_build_version": build_version,
        "parser_version": PARSER_VERSION,
        "parser_fingerprint": parser_fingerprint,
        "governance_fingerprint": governance_fingerprint,
        "review_baseline": baseline,
        "embedding_profile": None,
        "index_built": False,
        "retrieval_acceptance": "not_run",
        "documents": len(eligible),
        "chunks": chunks,
        "excluded_documents": excluded,
        "release_blockers": audit.payload()["release_blockers"],
    }
