import json
from pathlib import Path

import pytest

from app.knowledge.contract import KnowledgeError
from app.knowledge.evaluation import load_dataset

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_authored_gold_is_frozen_and_family_disjoint(version):
    manifest, data = load_dataset(ROOT / "datasets/minishop" / version)
    assert len(data["review.jsonl"]) == 30
    assert len(data["retrieval.jsonl"]) == 18
    assert manifest["annotation_type"] == "delegated_ai"
    assert {r["split"] for r in data["review.jsonl"]} == {"dev", "validation", "frozen", "regression"}


def test_gold_cannot_change_without_a_new_manifest(workdir):
    directory = ROOT / "datasets/minishop/v1"
    for name in ("manifest.json", "retrieval.jsonl", "review.jsonl"):
        (workdir / name).write_bytes((directory / name).read_bytes())
    path = workdir / "review.jsonl"
    rows = path.read_text(encoding="utf-8").splitlines()
    row = json.loads(rows[0])
    row["split"] = "frozen"
    rows[0] = json.dumps(row)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(KnowledgeError, match="checksum"):
        load_dataset(workdir)
