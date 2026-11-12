from dataclasses import replace

import pytest

from app.core.auth import Principal
from app.core.enums import ActorType
from app.knowledge.runtime import index_candidate
from app.main import create_app
from tests.helpers import make_settings, review_payload, valid_case
from tests.unit.test_knowledge_runtime import acceptance, candidate


async def test_task_freezes_release_across_active_switch_and_report_contains_sources():
    app = create_app(make_settings(knowledge_enabled=True), run_worker=False)
    service = app.state.knowledge
    first = await index_candidate(candidate())
    await service.store.put(first)
    await service.publish(first["version"], actor="delegated", reason="first", expected=None,
                          acceptance=acceptance(first), allow_delegated=True)
    case = valid_case(module="order", project_id="minishop", review_baseline="current_implementation",
                      product_version="1.0.0", title="客户端金额是否按服务端 SKU 价格计算")
    principal = Principal("reviewer", ActorType.HUMAN, frozenset({"reviewer"}), None)
    submitted = await app.state.review_service.submit(review_payload(case, options={"strict_kb": True}), principal)
    second = await index_candidate(candidate("订单金额以支付时价格重新计算；这是另一个版本的规则。"))
    await service.store.put(second)
    await service.publish(second["version"], actor="delegated", reason="new version", expected=first["version"],
                          acceptance=acceptance(second), allow_delegated=True)
    assert await app.state.worker.run_once() in {"done", "completed_with_warnings"}
    job = await app.state.storage.get_job(submitted.body["review_id"])
    assert job.kb_build_version == first["version"]
    assert job.report_json["versions"]["kb_build_version"] == first["version"]
    pack = job.report_json["appendix"]["knowledge_pack"]
    assert pack["evidence"][0]["text"] == first["chunks"][0]["text"]
    assert "kb_retrieve" in job.report_json["review_completeness"]["stages_completed"]
    replay = await app.state.review_service.submit(review_payload(case), principal)
    assert replay.body["review_id"] != job.id


async def test_changed_model_configuration_cannot_mislabel_old_task():
    app = create_app(make_settings(), run_worker=False)
    principal = Principal("reviewer", ActorType.HUMAN, frozenset({"reviewer"}), None)
    result = await app.state.review_service.submit(review_payload(), principal)
    app.state.worker.versions = replace(app.state.versions, model_config="changed")
    assert await app.state.worker.run_once() == "failed_or_retrying"
    job = await app.state.storage.get_job(result.body["review_id"])
    assert job.report_json is None


@pytest.mark.postgres
async def test_postgres_release_immutability_and_atomic_switch(migrated_database):
    from app.knowledge.postgres import PostgresKnowledgeStore
    from app.knowledge.runtime import KnowledgeService

    store = PostgresKnowledgeStore(migrated_database)
    try:
        release = await index_candidate(candidate())
        await store.put(release)
        service = KnowledgeService(store)
        await service.publish(release["version"], actor="delegated", reason="postgres test", expected=None,
                              acceptance=acceptance(release), allow_delegated=True)
        assert (await store.current("minishop", "current_implementation"))["version"] == release["version"]
        assert len(await store.history("minishop")) == 1
        pool = await store._get_pool()
        with pytest.raises(Exception, match="immutable"):
            await pool.execute("DELETE FROM knowledge_builds WHERE version=$1", release["version"])
        from app.llm.base import EmbeddingResponse

        class Embedder:
            async def embed(self, texts):
                return EmbeddingResponse([[1.0] + [0.0] * 1023 for _ in texts], "test", 1024)

        vector_release = await index_candidate(candidate(), embedder=Embedder(), profile="test-vector")
        await store.put(vector_release)
        vector_service = KnowledgeService(store, embedder=Embedder(), profile="test-vector")
        pack = await vector_service.retrieve(vector_release["version"], project="minishop", module="order",
                                             query="价格", product_version="1.0.0")
        assert "vector" in pack["evidence"][0]["retrieval_channels"]
        assert await store.rank_vectors(vector_release["version"], ["different-project-chunk"],
                                        [1.0] + [0.0] * 1023) == []
    finally:
        await store.close()
