from __future__ import annotations

import copy
import hashlib

import pytest

from app.knowledge.contract import KnowledgeError
from app.knowledge.runtime import KnowledgeService, MemoryKnowledgeStore, digest, index_candidate
from app.llm.evidence import verify_evidence


def candidate(text="订单价格以服务端 SKU 单价重算，客户端价格不可信。", *, module="order", project="minishop"):
    chunk = {
        "chunk_id": "chunk-1", "project_id": project, "module": module, "doc_id": "RULE-ORDER-001",
        "kb_build_version": "candidate-1", "rule_status": "reviewed", "source_evidence": [{"source_ref": "orders.py"}],
        "text": text, "heading_path": "金额计算", "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        "product_version": ["1.0.0"], "platforms": ["all"], "evidence_level": "E2",
        "knowledge_type": "BUSINESS_RULE", "source_ref": "orders.py#L1-L10",
    }
    return {"status": "candidate", "publication_status": "unpublished", "project_id": project,
            "kb_build_version": "candidate-1", "kb_content_version": "content-1", "chunks": [chunk],
            "review_baseline": {"type": "current_implementation", "product_version": "1.0.0",
                                "source_ref": "repo", "source_version": "a" * 40},
            "excluded_documents": []}


async def prepared():
    service = KnowledgeService(MemoryKnowledgeStore())
    release = await index_candidate(candidate())
    await service.store.put(release)
    return service, release


def acceptance(release):
    return {"build_version": release["version"], "passed": True, "annotation_type": "delegated_ai",
            "dataset_sha256": "b" * 64, "review_record_sha256": "c" * 64}


async def test_publication_requires_exact_acceptance_and_explicit_delegation():
    service, release = await prepared()
    args = {"actor": "codex-delegated-reviewer", "reason": "verified seed release", "expected": None,
            "acceptance": acceptance(release)}
    with pytest.raises(KnowledgeError, match="delegated"):
        await service.publish(release["version"], **args)
    await service.publish(release["version"], **args, allow_delegated=True)
    assert (await service.resolve("minishop", "current_implementation", "order"))["version"] == release["version"]
    with pytest.raises(KnowledgeError, match="active version changed"):
        await service.publish(release["version"], **args, allow_delegated=True)
    assert len(service.store.events) == 1


async def test_scope_date_platform_and_immutable_build():
    service, release = await prepared()
    params = {"project": "minishop", "module": "order", "query": "服务端金额 SKU 价格", "product_version": "1.0.0"}
    pack = await service.retrieve(release["version"], **params)
    assert len(pack["evidence"]) == 1
    assert pack["pack_hash"] == digest({k: v for k, v in pack.items() if k != "pack_hash"})
    assert not (await service.retrieve(release["version"], **{**params, "module": "payment"}))["evidence"]
    with pytest.raises(KnowledgeError, match="mismatch"):
        await service.retrieve(release["version"], **{**params, "project": "another"})
    with pytest.raises(KnowledgeError, match="mismatch"):
        await service.retrieve(release["version"], **{**params, "product_version": "2.0.0"})
    # Immutable store does not leak mutable references.
    returned = await service.store.get(release["version"])
    returned["chunks"][0]["text"] = "poison"
    assert (await service.store.get(release["version"]))["chunks"][0]["text"] != "poison"
    with pytest.raises(KnowledgeError):
        await service.store.put(returned)
    old = candidate()
    old["chunks"][0]["effective_until"] = "2020-01-01"
    expired = await index_candidate(old)
    await service.store.put(expired)
    assert not (await service.retrieve(expired["version"], **params, as_of="2026-11-12"))["evidence"]


async def test_integrity_and_token_budget_do_not_cut_rules():
    service, release = await prepared()
    pack = await service.retrieve(release["version"], project="minishop", module="order", query="价格",
                                  product_version="1.0.0", char_cap=4)
    assert pack["evidence"] == []
    bad = candidate()
    bad["chunks"][0]["text"] = "altered"
    with pytest.raises(KnowledgeError, match="hash"):
        await index_candidate(bad)


def test_reference_membership_is_not_enough_for_grounding():
    chunk = candidate()["chunks"][0]
    case = {"title": "价格测试", "steps": [{"action": "提交订单", "expected": "价格为 1 分"}]}
    issue = {"kb_refs": ["chunk-1"], "kb_quote": "订单价格以服务端 SKU 单价重算", "kb_grounded": True,
             "evidence_type": "business_rule", "evidence_strength": "strong", "evidence_quote": "价格为 1 分"}
    result = verify_evidence(issue, case, allowed_kb_refs={"chunk-1"}, knowledge_evidence=[chunk])
    assert result.status == "grounded"
    for patch in ({"kb_quote": "支付成功会自动退款"}, {"kb_refs": ["invented"]},
                  {"evidence_type": "requirement"}):
        result = verify_evidence({**issue, **patch}, case, allowed_kb_refs={"chunk-1"}, knowledge_evidence=[chunk])
        assert result.status == "insufficient"
        assert not result.kb_grounded
    weak = copy.deepcopy(chunk)
    weak["evidence_level"] = "E4"
    assert verify_evidence(issue, case, allowed_kb_refs={"chunk-1"}, knowledge_evidence=[weak]).status == "insufficient"


async def test_explicit_endpoint_keeps_matching_contract_in_small_context():
    data = candidate()
    contract = copy.deepcopy(data["chunks"][0])
    contract.update(chunk_id="api-create", doc_id="API-CREATE", knowledge_type="INTERFACE",
                    text="POST /api/orders\n成功返回201。", heading_path="请求方式")
    contract["content_hash"] = hashlib.sha256(contract["text"].encode()).hexdigest()
    wrong = copy.deepcopy(contract)
    wrong.update(chunk_id="api-delete", doc_id="API-DELETE", text="DELETE /api/orders/{order_id}\n成功返回204。")
    wrong["content_hash"] = hashlib.sha256(wrong["text"].encode()).hexdigest()
    data["chunks"].extend([contract, wrong])
    service = KnowledgeService(MemoryKnowledgeStore())
    release = await index_candidate(data)
    await service.store.put(release)
    pack = await service.retrieve(release["version"], project="minishop", module="order", product_version="1.0.0",
                                  query="POST /api/orders，服务端SKU价格金额", top_k=2)
    assert pack["evidence"][0]["chunk_id"] == "api-create"
    assert "interface_contract" in pack["evidence"][0]["retrieval_channels"]
    from app.knowledge.runtime import _matches_endpoint
    assert _matches_endpoint(("GET", "/api/orders/{order_id}"), ("GET", "/api/orders/10"))
    assert not _matches_endpoint(("GET", "/api/orders/{order_id}"), ("POST", "/api/orders/10"))


@pytest.mark.parametrize("patch, message", [
    ({"retriever": "retired-retriever"}, "retrieval implementation unavailable"),
    ({"profile": "unavailable-vector-profile"}, "embedding profile unavailable"),
])
async def test_activation_cannot_replace_working_build_with_incompatible_runtime(patch, message):
    service, release = await prepared()
    await service.publish(release["version"], actor="test", reason="initial", expected=None,
                          acceptance=acceptance(release), allow_delegated=True)
    incompatible = {**release, **patch}
    incompatible["version"] = "kb-runtime-" + digest({k: v for k, v in incompatible.items() if k != "version"})
    await service.store.put(incompatible)
    with pytest.raises(KnowledgeError, match=message):
        await service.publish(incompatible["version"], actor="test", reason="rollback",
                              expected=release["version"], acceptance=acceptance(incompatible), allow_delegated=True)
    assert (await service.store.current("minishop", "current_implementation"))["version"] == release["version"]
    assert len(await service.store.history("minishop")) == 1
