"""Strict parsing and a lossless adapter from project content to platform metadata."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from app.core.enums import DocType, RuleStatus


class KnowledgeError(ValueError):
    """A content error that must block a build."""


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate mapping keys instead of silently keeping the last value."""


def _unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise KnowledgeError(f"line {key_node.start_mark.line + 1}: mapping key must be scalar") from exc
        if duplicate:
            raise KnowledgeError(f"line {key_node.start_mark.line + 1}: duplicate YAML key {key!r}")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_yaml_text(text: str) -> Any:
    try:
        return yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise KnowledgeError(str(exc)) from exc


def load_yaml(path: Path) -> Any:
    return load_yaml_text(path.read_text(encoding="utf-8-sig"))


def content_hash(metadata: dict[str, Any], body: str) -> str:
    """Hash all authored metadata and text, independent of YAML formatting and CRLF."""
    payload = json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256((payload + "\n" + body.replace("\r\n", "\n")).encode()).hexdigest()


@dataclass(frozen=True)
class KnowledgeDocument:
    path: Path
    metadata: dict[str, Any]
    body: str
    canonical: dict[str, Any]

    @property
    def digest(self) -> str:
        return content_hash(self.metadata, self.body)


def normalize_metadata(
    metadata: dict[str, Any], contract: dict[str, Any], *, project_id: str, modules: set[str]
) -> dict[str, Any]:
    required = {
        "id",
        "title",
        "knowledge_type",
        "project_id",
        "module_id",
        "source_type",
        "source_ref",
        "source_version",
        "product_version",
        "platforms",
        "evidence_level",
        "status",
        "owner",
        "reviewer",
        "created_at",
        "updated_at",
        "effective_from",
        "effective_until",
        "tags",
    }
    missing = required - metadata.keys()
    if missing:
        raise KnowledgeError(f"missing metadata: {sorted(missing)}")
    for key in ("id", "title", "source_ref", "owner"):
        if not isinstance(metadata[key], str) or not metadata[key].strip():
            raise KnowledgeError(f"{key} must be a nonempty string")
    if metadata["project_id"] != project_id:
        raise KnowledgeError(f"project_id must be {project_id!r}")
    module = metadata["module_id"]
    if module is not None and (not isinstance(module, str) or module not in modules):
        raise KnowledgeError(f"module_id {module!r} is not in the project whitelist")
    kind = metadata["knowledge_type"]
    status = metadata["status"]
    types = contract["knowledge_type_mapping"]
    statuses = contract["status_mapping"]
    if not isinstance(kind, str) or kind not in types:
        raise KnowledgeError(f"unknown knowledge_type {kind!r}")
    if not isinstance(status, str) or status not in statuses:
        raise KnowledgeError(f"unknown content status {status!r}; published is a release operation")
    if metadata["evidence_level"] not in {"E1", "E2", "E3", "E4"}:
        raise KnowledgeError("invalid evidence_level")
    source_types = {
        "PRD",
        "REQUIREMENT_SPEC",
        "DESIGN_DOC",
        "API_SPEC",
        "DATABASE_SCHEMA",
        "TEST_STANDARD",
        "AUTOMATION_DOC",
        "BUG_TRACKER",
        "MEETING_DECISION",
        "EXPERT_REVIEW",
        "OFFICIAL_WIKI",
        "OTHER",
    }
    if metadata["source_type"] not in source_types:
        raise KnowledgeError("invalid source_type")
    versions = metadata["product_version"]
    if isinstance(versions, str):
        versions = [versions]
    for key, value in (("product_version", versions), ("platforms", metadata["platforms"])):
        if not isinstance(value, list) or not value or any(not isinstance(v, str) or not v.strip() for v in value):
            raise KnowledgeError(f"{key} must contain nonempty strings")
    if not isinstance(metadata["tags"], list) or any(not isinstance(tag, str) for tag in metadata["tags"]):
        raise KnowledgeError("tags must be a list of strings")
    source_version = metadata["source_version"]
    if source_version is None:
        if status == "approved":
            raise KnowledgeError("approved source_version must be explicitly frozen")
    elif not isinstance(source_version, str) or not source_version.strip():
        raise KnowledgeError("source_version must be a version string or explicit null")
    for key in ("created_at", "updated_at", "effective_from", "effective_until", "reviewed_at"):
        value = metadata.get(key)
        if value is None and key not in {"created_at", "updated_at"}:
            continue
        try:
            date.fromisoformat(str(value))
        except (TypeError, ValueError) as exc:
            raise KnowledgeError(f"invalid date {key}: {value!r}") from exc
    if status == "approved":
        if not isinstance(metadata["reviewer"], str) or not metadata["reviewer"].strip() or not metadata.get("reviewed_at"):
            raise KnowledgeError("approved requires reviewer and reviewed_at")
        if metadata.get("review_status") == "changes_applied_pending_reapproval":
            raise KnowledgeError("pending reapproval cannot be approved")
    canonical = dict(metadata)
    aliases = {"doc_id": metadata["id"], "module": module, "doc_type": types[kind]}
    for key, value in aliases.items():
        if key in metadata and metadata[key] != value:
            raise KnowledgeError(f"conflicting alias {key}: {metadata[key]!r} vs {value!r}")
    canonical.update(aliases)
    canonical["rule_status"] = statuses[status]
    if metadata.get("rule_status", statuses[status]) != statuses[status]:
        raise KnowledgeError("rule_status cannot bypass the content lifecycle mapping")
    if canonical["doc_type"] not in {v.value for v in DocType}:
        raise KnowledgeError("mapping produces an unsupported doc_type")
    if canonical["rule_status"] not in {v.value for v in RuleStatus} or canonical["rule_status"] == "published":
        raise KnowledgeError("content normalization cannot publish knowledge")
    canonical["product_version"] = versions
    return canonical


def read_document(path: Path, contract: dict[str, Any], *, project_id: str, modules: set[str]) -> KnowledgeDocument:
    text = path.read_text(encoding="utf-8-sig")
    match = re.match(r"\A---\n(.*?)^---[ \t]*\n(.*)\Z", text, flags=re.MULTILINE | re.DOTALL)
    if match is None:
        raise KnowledgeError("missing or unclosed YAML front matter")
    metadata = load_yaml_text("\n" + match[1])
    if not isinstance(metadata, dict) or not match[2].strip():
        raise KnowledgeError("metadata must be an object and body must not be empty")
    canonical = normalize_metadata(metadata, contract, project_id=project_id, modules=modules)
    return KnowledgeDocument(path, metadata, match[2], canonical)


def validate_baseline(baseline: Any, contract: dict[str, Any]) -> dict[str, str]:
    if not isinstance(baseline, dict):
        raise KnowledgeError("an explicit review_baseline is required")
    for key in ("type", "product_version", "source_ref", "source_version"):
        if not isinstance(baseline.get(key), str) or not baseline[key].strip():
            raise KnowledgeError(f"review_baseline.{key} must be frozen")
    if baseline["type"] not in contract["baseline_types"]:
        raise KnowledgeError("unknown review baseline type")
    pattern = r"[0-9a-f]{40}" if baseline["type"] == "current_implementation" else r"[0-9a-f]{64}"
    if not re.fullmatch(pattern, baseline["source_version"]):
        raise KnowledgeError("baseline source_version must be an immutable commit or decision SHA-256")
    return {str(k): str(v) for k, v in baseline.items()}
