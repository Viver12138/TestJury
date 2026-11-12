"""Offline content, evidence and governance checks; no source project code is executed."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from app.knowledge.contract import KnowledgeDocument, KnowledgeError, load_yaml, read_document, validate_baseline


@dataclass
class AuditResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    release_blockers: list[str] = field(default_factory=list)
    documents: list[KnowledgeDocument] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)
    sources_verified: bool = False
    snapshot_verified: bool = False
    repository_verified: bool = False
    manual_review_verified: bool = False

    def payload(self) -> dict[str, Any]:
        return {
            "ok": not self.errors,
            "release_ready": not self.errors and not self.release_blockers,
            "documents": len(self.documents),
            "content_statuses": dict(Counter(d.metadata["status"] for d in self.documents)),
            "source_counts": self.source_counts,
            "sources_verified": self.sources_verified,
            "snapshot_verified": self.snapshot_verified,
            "repository_verified": self.repository_verified,
            "manual_review_verified": self.manual_review_verified,
            "errors": self.errors,
            "warnings": self.warnings,
            "release_blockers": sorted(set(self.release_blockers)),
        }


def repo_path(root: Path, value: str) -> Path:
    """Reject absolute paths, parent traversal and symlink escapes in authored references."""
    if not isinstance(value, str) or "\\" in value or ":" in value:
        raise KnowledgeError(f"invalid repository path {value!r}")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise KnowledgeError(f"invalid repository path {value!r}")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise KnowledgeError(f"path escapes repository: {value}")
    return path


def source_ref(value: str) -> tuple[str, int | None, int | None]:
    match = re.fullmatch(r"Minishop/([^#;]+?)(?:#L([1-9]\d*)(?:-L([1-9]\d*))?)?", value.strip())
    if not match:
        raise KnowledgeError(f"invalid source locator {value!r}")
    start = int(match[2]) if match[2] else None
    end = int(match[3]) if match[3] else start
    if start is not None and end is not None and end < start:
        raise KnowledgeError(f"inverted source locator {value!r}")
    return match[1], start, end


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={root.resolve().as_posix()}", "-C", str(root), *args],
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise KnowledgeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def _snapshot_sources(root: Path, binding: dict[str, Any], inventory: dict[str, Any]) -> dict[str, bytes]:
    spec = binding.get("snapshot_archive")
    if not spec:
        return {}
    path = repo_path(root, spec["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != spec["sha256"]:
        raise KnowledgeError("snapshot archive SHA-256 mismatch")
    entries = inventory["sources"]
    if spec.get("source_count") != len(entries):
        raise KnowledgeError("snapshot archive source count differs from inventory")
    blobs = {}
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != {item["path"] for item in entries}:
            raise KnowledgeError("snapshot archive must contain exactly the inventoried paths, without duplicates")
        for entry in entries:
            name = entry["path"]
            repo_path(root, name)
            if archive.getinfo(name).file_size != entry["bytes"]:
                raise KnowledgeError(f"snapshot archive member size mismatch: {name}")
            data = archive.read(name)
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise KnowledgeError(f"snapshot archive member SHA-256 mismatch: {name}")
            blobs[name.removeprefix("Minishop/")] = data
    return blobs


def _check_sources(
    root: Path, binding: dict[str, Any], inventory: dict[str, Any], result: AuditResult, source_root: Path | None
) -> dict[str, dict[str, Any]]:
    if binding.get("repository") != "https://github.com/Viver12138/minishop.git":
        result.errors.append("source_binding.repository: unexpected MiniShop repository")
    commit = binding.get("commit", "")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise KnowledgeError("source_binding.commit must be a full immutable SHA")
    if binding.get("source_version") != f"snapshot-{inventory.get('snapshot')}":
        result.errors.append("source_binding.source_version does not match the inventoried snapshot")
    entries = {item["id"]: item for item in inventory["sources"]}
    files = binding["files"]
    if len(entries) != len(inventory["sources"]) or len(files) != len(entries):
        result.errors.append("source inventory/binding IDs must be unique and one-to-one")
    by_path: dict[str, dict[str, Any]] = {}
    ids: set[str] = set()
    snapshot = _snapshot_sources(root, binding, inventory)
    result.snapshot_verified = bool(snapshot) and len(snapshot) == len(entries)
    blobs: dict[str, bytes] = dict(snapshot)
    if source_root is not None:
        actual = _git(source_root, "rev-parse", f"{commit}^{{commit}}").decode().strip()
        if actual != commit:
            raise KnowledgeError(f"source object {actual} differs from frozen commit {commit}")
        origin = _git(source_root, "remote", "get-url", "origin").decode().strip().removesuffix(".git").rstrip("/")
        if origin != binding["repository"].removesuffix(".git"):
            raise KnowledgeError("source checkout origin differs from the bound repository")
    for item in files:
        entry = entries.get(item.get("id"))
        if entry is None or item["id"] in ids:
            result.errors.append(f"source binding duplicate/unknown ID: {item.get('id')}")
            continue
        ids.add(item["id"])
        path = item["path"]
        repo_path(root, path)  # Validate syntax independently of the source checkout.
        if entry["path"] != f"Minishop/{path}" or item.get("snapshot_sha256") != entry["sha256"]:
            result.errors.append(f"{item['id']}: binding differs from original snapshot inventory")
        state = item.get("state")
        digest = item.get("repository_sha256")
        if state not in {"matched", "changed", "missing"}:
            result.errors.append(f"{path}: invalid source state")
        if state == "matched" and digest != entry["sha256"]:
            result.errors.append(f"{path}: matched source must have identical hashes")
        if state in {"matched", "changed"} and (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
            result.errors.append(f"{path}: repository SHA-256 is missing/invalid")
        if state == "changed" and (digest == entry["sha256"] or not item.get("reason")):
            result.errors.append(f"{path}: changed source needs distinct hashes and an explanation")
        if state == "missing" and (digest is not None or not item.get("reason")):
            result.errors.append(f"{path}: missing source needs an explanation and null repository hash")
        if state != "matched":
            suffix = "original bytes preserved in verified snapshot archive" if path in snapshot else "snapshot unavailable"
            result.warnings.append(f"Git source {path}: {state}; {suffix}")
            if path not in snapshot:
                result.release_blockers.append(f"source_snapshot:{path}:{state}")
        by_path[path] = item
        if source_root is not None:
            if state == "missing":
                found = _git(source_root, "ls-tree", "--name-only", commit, "--", path).strip()
                if found:
                    result.errors.append(f"{path}: declared missing but exists in frozen commit")
                continue
            blob = _git(source_root, "show", f"{commit}:{path}")
            if path not in snapshot:
                blobs[path] = blob
            if hashlib.sha256(blob).hexdigest() != digest:
                result.errors.append(f"{path}: frozen Git blob SHA-256 differs from binding")
    if ids != set(entries):
        result.errors.append("source binding does not cover the exact inventory ID set")
    result.source_counts = dict(Counter(item.get("state", "invalid") for item in files))
    for document in result.documents:
        if document.metadata["source_version"] != binding["source_version"]:
            result.errors.append(f"{document.metadata['id']}: source_version differs from bound snapshot")
        for ref in document.metadata["source_ref"].split(";"):
            if not ref.strip().startswith("Minishop/"):
                locator = ref.strip().split("#", 1)
                path = repo_path(root, locator[0])
                declared = binding.get("internal_sources", {}).get(locator[0])
                if declared is None or hashlib.sha256(path.read_bytes()).hexdigest() != declared:
                    result.errors.append(f"{document.metadata['id']}: unbound internal source {locator[0]}")
                if len(locator) > 1 and f'id="{locator[1]}"' not in path.read_text(encoding="utf-8"):
                    result.errors.append(f"{document.metadata['id']}: internal heading anchor is missing")
                continue
            path, start, end = source_ref(ref)
            item = by_path.get(path)
            if item is None:
                result.errors.append(f"{document.metadata['id']}: unregistered source {path}")
            elif start and end is not None and end > entries[item["id"]]["lines"]:
                result.errors.append(f"{document.metadata['id']}: source locator exceeds snapshot lines: {ref}")
            elif start and path in blobs:
                if end is None or end > len(blobs[path].splitlines()):
                    result.errors.append(f"{document.metadata['id']}: source locator out of bounds: {ref}")
    if source_root is None:
        result.release_blockers.append("source_repository_verification:not_run; use --source-root")
    else:
        result.repository_verified = not result.errors
    result.sources_verified = not result.errors and (result.snapshot_verified or result.repository_verified)
    return by_path


def _check_governance(root: Path, contract: dict[str, Any], result: AuditResult) -> None:
    base = root / "kb_content/minishop/_governance"
    ids = {document.metadata["id"] for document in result.documents}
    ids.add(load_yaml(root / "kb_content/minishop/project/modules.yaml")["id"])
    known: set[str] = set(ids)
    by_id = {document.metadata["id"]: document for document in result.documents}
    ledgers: list[tuple[str, list[dict[str, Any]]]] = []
    for filename, key in (
        ("conflicts.yaml", "conflicts"),
        ("pending_confirmation.yaml", "items"),
        ("knowledge_gaps.yaml", "gaps"),
    ):
        data = load_yaml(base / filename)
        if data.get("project_id") != "minishop":
            result.errors.append(f"{filename}: project_id mismatch")
        items = data[key]
        ledgers.append((filename, items))
        for item in items:
            if item["id"] in known:
                result.errors.append(f"duplicate governance ID {item['id']}")
            known.add(item["id"])
    for document in result.documents:
        for reference in document.metadata.get("related_ids", []):
            if reference not in known:
                result.errors.append(f"{document.metadata['id']}: unresolved related_id {reference}")
    for filename, items in ledgers:
        for item in items:
            for reference in item.get("related_ids", item.get("related_knowledge_ids", [])):
                if reference not in known:
                    result.errors.append(f"{item['id']}: unresolved related_id {reference}")
            if filename == "knowledge_gaps.yaml":
                if item["status"] not in {"closed", "downgraded"} and item.get("required_by") != "后续版本":
                    result.release_blockers.append(f"knowledge_gap:{item['id']}")
                continue
            for key, values in contract["governance_enums"].items():
                if item.get(key) not in values:
                    result.errors.append(f"{item['id']}.{key}: expected one of {values}")
            if item.get("decision_status") == "decided" and (not item.get("decided_by") or not item.get("decided_at")):
                result.errors.append(f"{item['id']}: a decision needs attribution and date")
            if item.get("decision_status") != "decided":
                result.release_blockers.append(f"decision:{item['id']}")
            if item.get("documentation_status") != "reviewed":
                result.release_blockers.append(f"documentation:{item['id']}")
            else:
                refs = item.get("related_ids", item.get("related_knowledge_ids", []))
                linked = [by_id[ref] for ref in refs if ref in by_id]
                if not linked or any(document.metadata["status"] != "approved" for document in linked):
                    result.errors.append(
                        f"{item['id']}: documentation cannot be reviewed while linked content awaits review"
                    )
            implementation = item.get("implementation_status")
            verification = item.get("verification_status")
            if implementation == "pending" or verification == "failed":
                result.release_blockers.append(f"implementation:{item['id']}")
            if verification == "passed":
                evidence = item.get("verification_evidence")
                if implementation == "pending" or not evidence or not repo_path(root, evidence).is_file():
                    result.errors.append(f"{item['id']}: passed verification requires completed work and evidence")
            if implementation == "implemented" and verification != "passed":
                result.release_blockers.append(f"verification:{item['id']}")


def _check_decision_transcript(root: Path, evidence_path: Path, result: AuditResult) -> None:
    rows = json.loads(evidence_path.read_text(encoding="utf-8"))
    base = root / "kb_content/minishop/_governance"
    for filename, key, sheet, id_field, decision_field, text_field, author_field in (
        ("pending_confirmation.yaml", "items", "Q", "编号", "decision_note", "结论说明 / 决策依据", "确认人"),
        ("conflicts.yaml", "conflicts", "C", "冲突编号", "resolution", "裁决结论", "负责人"),
    ):
        originals = {item[id_field]: item for item in rows[sheet]}
        items = load_yaml(base / filename)[key]
        if {item["id"] for item in items} != set(originals):
            result.errors.append(f"{filename}: decision IDs differ from controlled review transcript")
        for item in items:
            original = originals.get(item["id"], {})
            expected = re.sub(r"\s+", "", str(original.get(text_field, "")))
            actual = re.sub(r"\s+", "", str(item.get(decision_field, "")))
            if actual != expected or item.get("decided_by") != original.get(author_field):
                result.errors.append(f"{item['id']}: decision differs from controlled review transcript")
            if sheet == "Q" and (
                item.get("decision") != original.get("人工结论")
                or str(item.get("decided_at")) != str(original.get("确认日期"))[:10]
            ):
                result.errors.append(f"{item['id']}: decision attribution/date differs from controlled review transcript")


def audit_repository(root: Path, *, source_root: Path | None = None) -> AuditResult:
    result = AuditResult()
    try:
        contract = load_yaml(root / "design/kb_contract.yaml")
        if contract.get("field_mapping") != {"id": "doc_id", "module_id": "module", "knowledge_type": "doc_type"}:
            raise KnowledgeError("field_mapping differs from the platform compatibility contract")
        # Content approval must never be a hidden alias for publication.
        if contract["status_mapping"].get("approved") != "reviewed" or "published" in contract["status_mapping"].values():
            raise KnowledgeError("status_mapping: approved must map to reviewed, never published")
        project = root / "kb_content/minishop"
        module_data = load_yaml(project / "project/modules.yaml")
        if module_data.get("project_id") != "minishop":
            result.errors.append("module registry project_id mismatch")
        modules = {item["id"] for item in module_data["modules"]}
        if len(modules) != len(module_data["modules"]):
            result.errors.append("project module IDs must be unique")
        ids: set[str] = set()
        for path in sorted(project.rglob("*.md")):
            if "_governance" in path.parts or path.name == "README.md":
                continue
            try:
                document = read_document(path, contract, project_id="minishop", modules=modules)
                doc_id = document.metadata["id"]
                if doc_id in ids:
                    raise KnowledgeError(f"duplicate doc_id {doc_id}")
                ids.add(doc_id)
                result.documents.append(document)
                if document.metadata["status"] != "approved":
                    result.release_blockers.append(f"pending_review:{doc_id}")
            except (KnowledgeError, OSError) as exc:
                result.errors.append(f"{path.relative_to(root).as_posix()}: {exc}")
        if not result.documents:
            result.errors.append("knowledge content must not be empty")
        lock = load_yaml(project / "_governance/review_lock.yaml")
        for document in result.documents:
            if document.metadata["status"] == "approved":
                record = lock["documents"].get(document.metadata["id"], {})
                if record.get("content_hash") != document.digest or record.get("reviewer") != document.metadata["reviewer"]:
                    result.errors.append(f"{document.metadata['id']}: approved content changed after its review lock")
        _check_governance(root, contract, result)
        delivery = root / "kb_content/_delivery"
        binding = load_yaml(delivery / "source_binding.yaml")
        _check_sources(root, binding, load_yaml(delivery / "source_inventory.yaml"), result, source_root)
        gaps = load_yaml(project / "_governance/knowledge_gaps.yaml")["gaps"]
        provenance_gap = next((item for item in gaps if item["id"] == "GAP-006"), {})
        if provenance_gap.get("status") == "closed" and not result.snapshot_verified:
            result.errors.append("GAP-006: closing provenance requires the complete verified original snapshot")
        policy = load_yaml(project / "project/review_policy.yaml")
        if policy.get("project_id") != "minishop" or policy.get("default_baseline") is not None:
            result.errors.append("review policy must scope its project and require explicit baseline selection")
        for key, baseline in policy["baselines"].items():
            validated = validate_baseline(baseline, contract)
            if validated["type"] != key:
                result.errors.append("review_policy baseline key/type mismatch")
            if key == "current_implementation" and validated["source_version"] != binding["commit"]:
                result.errors.append("implementation baseline must reference the bound source commit")
            if key == "current_implementation" and validated["source_ref"] != binding["repository"]:
                result.errors.append("implementation baseline must reference the bound source repository")
        evidence = binding["manual_decisions"]
        evidence_path = repo_path(root, evidence["path"])
        evidence_hash = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        if evidence_hash != evidence["sha256"]:
            result.errors.append("manual decision extract changed after source binding")
        _check_decision_transcript(root, evidence_path, result)
        target = policy["baselines"]["target_specification"]
        if target["source_version"] != evidence_hash or target["source_ref"] != evidence["path"]:
            result.errors.append("target baseline must freeze the bound manual decision extract")
        original = evidence.get("original_workbook")
        if original:
            workbook_path = repo_path(root, original["path"])
            workbook_hash = hashlib.sha256(workbook_path.read_bytes()).hexdigest()
            comparison_path = repo_path(root, original["comparison_report"])
            comparison_hash = hashlib.sha256(comparison_path.read_bytes()).hexdigest()
            comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
            valid = (
                evidence.get("original_workbook_available") is True
                and workbook_hash == original["sha256"]
                and comparison_hash == original["comparison_sha256"]
                and comparison.get("matches") is True
                and comparison.get("original_workbook_sha256") == workbook_hash
                and comparison.get("transcript_sha256") == evidence_hash
                and comparison.get("sheet_counts") == {"Q": 15, "C": 10, "G": 15, "D": 37}
                and comparison.get("compared_rows") == 77
            )
            if not valid:
                result.errors.append("original workbook or immutable transcript comparison evidence changed")
            result.manual_review_verified = valid
        else:
            result.release_blockers.append("manual_decisions:original_workbook_or_signed_record_missing")
        release = load_yaml(project / "_governance/admission.yaml")
        if release.get("project_id") != "minishop" or release.get("module_id") not in modules:
            result.errors.append("admission project/module mismatch")
        capabilities = release.get("capabilities", [])
        types = [item.get("review_type") for item in capabilities]
        expected = {
            "interface_contract",
            "requirement_coverage",
            "business_scenario",
            "boundary_exception",
            "state_transition",
            "automation_feasibility",
        }
        if set(types) != expected or len(types) != len(set(types)):
            result.errors.append("admission must enumerate each supported review capability once")
        for item in capabilities:
            refs = item.get("required_doc_ids", [])
            if not refs or not set(refs) <= ids:
                result.errors.append(f"admission {item.get('review_type')}: unknown/missing required documents")
            if not item.get("restrictions") or item.get("candidate_admission") not in {"blocked", "conditional", "allowed"}:
                result.errors.append(f"admission {item.get('review_type')}: restrictions or content admission is invalid")
            if item.get("formal_admission") != "blocked":
                result.errors.append(
                    "candidate capabilities cannot grant formal admission before the active release pipeline"
                )
        if not release.get("review_baseline"):
            result.release_blockers.append("review_baseline:not_selected_for_release")
        else:
            frozen = validate_baseline(release["review_baseline"], contract)
            if frozen != policy["baselines"].get(frozen["type"]):
                result.errors.append("release baseline differs from registered immutable baseline")
        for stage in ("runtime_index", "embedding", "retrieval_acceptance", "review_acceptance", "publication"):
            result.release_blockers.append(f"{stage}:not_completed")
        if release.get("active_build") is not None or release.get("publication_status") != "unpublished":
            result.errors.append("candidate audit cannot activate or publish knowledge; formal release pipeline is required")
    except (KnowledgeError, OSError, KeyError, TypeError, AttributeError, ValueError, subprocess.SubprocessError) as exc:
        result.errors.append(f"knowledge contract: {exc}")
    return result
