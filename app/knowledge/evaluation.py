"""Reproducible retrieval evaluation with leakage and provenance checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.knowledge.contract import KnowledgeError
from app.knowledge.runtime import KnowledgeService, digest


def load_dataset(directory: Path) -> tuple[dict, dict[str, list[dict]]]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    groups: dict[str, str] = {}
    datasets = {}
    for name, expected_hash in manifest["files"].items():
        path = (directory / name).resolve()
        if path.parent != directory.resolve():
            raise KnowledgeError("dataset path escapes manifest directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise KnowledgeError("frozen dataset checksum mismatch")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len({r["id"] for r in rows}) != len(rows):
            raise KnowledgeError("duplicate dataset ids")
        for row in rows:
            family, split = row["family"], row["split"]
            if split not in {"dev", "validation", "frozen", "regression"}:
                raise KnowledgeError("invalid split")
            if family in groups and groups[family] != split:
                raise KnowledgeError("scenario family leaks across dataset splits")
            groups[family] = split
        datasets[name] = rows
    return manifest, datasets


async def evaluate_retrieval(service: KnowledgeService, version: str, directory: Path) -> dict:
    manifest, data = load_dataset(directory)
    release = await service.store.get(version)
    if release is None or release["baseline"]["type"] != manifest["baseline"]:
        raise KnowledgeError("dataset baseline does not match the evaluated build")
    if release["baseline"]["source_version"] != manifest["source_commit"]:
        raise KnowledgeError("dataset source commit does not match the evaluated build")
    rows = []
    for item in data["retrieval.jsonl"]:
        expected = set(item["relevant_doc_ids"])
        try:
            pack = await service.retrieve(version, project=item["project_id"], module=item["module"],
                                          query=item["query"], product_version=item["product_version"],
                                          platform="api", as_of="2026-11-12")
            docs = list(dict.fromkeys(c["doc_id"] for c in pack["evidence"]))
        except KnowledgeError:
            if expected or item["project_id"] == release["project_id"]:
                raise
            docs = []
        recalled = len(expected & set(docs)) / len(expected) if expected else float(not docs)
        rows.append({"id": item["id"], "split": item["split"], "expected": sorted(expected),
                     "retrieved": docs, "recall_at_10": recalled,
                     "reciprocal_rank": next((1 / (i + 1) for i, d in enumerate(docs) if d in expected), 0)
                     if expected else float(not docs)})
    metrics = {}
    for split in ("dev", "validation", "frozen", "regression"):
        selected = [r for r in rows if r["split"] == split]
        metrics[split] = {"count": len(selected),
                          "recall_at_10": sum(r["recall_at_10"] for r in selected) / max(1, len(selected)),
                          "mrr": sum(r["reciprocal_rank"] for r in selected) / max(1, len(selected))}
    return {"build_version": version, "dataset_sha256": digest(manifest),
            "annotation_type": manifest["annotation_type"], "metrics": metrics, "cases": rows,
            "passed": (all(m["count"] and m["recall_at_10"] >= 0.8 for m in metrics.values())
                       and all(not row["retrieved"] for row in rows if not row["expected"])),
            "acceptance_scope": "retrieval_only", "review_effectiveness": "not_measured"}
