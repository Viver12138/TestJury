import asyncio
from dataclasses import replace

import pytest

from app.core.auth import Principal
from app.core.enums import ActorType, Stage, StageStatus
from app.core.state_machine import FencingMismatch
from app.knowledge.runtime import digest
from app.llm.mock import MockChatClient
from app.main import create_app
from app.pipeline.checkpoints import Checkpoints
from app.pipeline.vote import run_vote
from app.storage.models import CandidateRecord
from tests.helpers import make_settings, review_payload, valid_case


async def exercise_recovery(settings):
    app = create_app(settings, run_worker=False)

    class CountingModel(MockChatClient):
        reviews = 0
        votes = 0

        async def review(self, role, case):
            self.reviews += 1
            return await super().review(role, case)

        async def vote(self, role, material):
            self.votes += 1
            return await super().vote(role, material)

    model = CountingModel()
    app.state.pipeline.model = model
    actor = Principal("test-service", ActorType.SERVICE, frozenset({"reviewer"}), None)
    case = valid_case(steps=[{"index": 1, "action": "提交请求", "expected": None}])
    submitted = await app.state.review_service.submit(review_payload(case), actor)
    original = app.state.pipeline._stage
    failed = False

    async def fail_once(job, stage, status, **kwargs):
        nonlocal failed
        if stage == Stage.RENDER and status == StageStatus.RUNNING and not failed:
            failed = True
            raise RuntimeError("simulated process loss after completed votes")
        return await original(job, stage, status, **kwargs)

    app.state.pipeline._stage = fail_once
    try:
        assert await app.state.worker.run_once() == "failed_or_retrying"
        counts = model.reviews, model.votes
        assert all(counts)
        candidates = [c.id for c in await app.state.storage.list_candidates(submitted.body["review_id"])]
        original_runs = await app.state.storage.list_model_runs(submitted.body["review_id"])
        assert await app.state.worker.run_once() in {"done", "completed_with_warnings"}
        assert (model.reviews, model.votes) == counts
        job = await app.state.storage.get_job(submitted.body["review_id"])
        assert "vote" in job.report_json["appendix"]["recovery"]["reused_outputs"]
        assert "fusion" in job.report_json["appendix"]["recovery"]["reused_outputs"]
        assert candidates == [c.id for c in await app.state.storage.list_candidates(job.id)]
        assert len(await app.state.storage.list_model_runs(job.id)) == len(original_runs)
    finally:
        close = getattr(app.state.storage, "close", None)
        if close:
            await close()


async def test_memory_recovery_reuses_successful_models_and_stable_candidates():
    await exercise_recovery(make_settings())


@pytest.mark.postgres
async def test_postgres_recovery_reuses_successful_models_and_stable_candidates(migrated_database):
    await exercise_recovery(make_settings(storage_backend="postgres", database_url=migrated_database))


async def test_checkpoints_reject_stale_owner_changed_inputs_and_corrupt_outputs():
    app = create_app(make_settings(), run_worker=False)
    actor = Principal("test-service", ActorType.SERVICE, frozenset({"reviewer"}), None)
    await app.state.review_service.submit(review_payload(), actor)
    job = await app.state.worker.claim_next()
    cache = Checkpoints(app.state.storage, job, app.state.versions)
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        return {"value": calls}

    assert await cache.run("test", {"upstream": 1}, operation) == {"value": 1}
    assert await cache.run("test", {"upstream": 1}, operation) == {"value": 1}
    assert await cache.run("test", {"upstream": 2}, operation) == {"value": 2}
    changed = Checkpoints(app.state.storage, job, replace(app.state.versions, model_config="changed"))
    assert await changed.run("test", {"upstream": 1}, operation) == {"value": 3}
    await app.state.storage.update_job(job.id, fencing_token=job.fencing_token, status="retrying")
    reclaimed = await app.state.worker.claim_next()
    with pytest.raises(FencingMismatch):
        await cache.run("stale", {}, operation)
    saved = next(iter(app.state.storage._checkpoints.values()))
    saved["output_digest"] = digest("corrupted")
    cache = Checkpoints(app.state.storage, reclaimed, app.state.versions)
    with pytest.raises(RuntimeError, match="integrity"):
        await cache.run("test", {"upstream": 1}, operation)


async def exercise_partial_votes(settings):
    app = create_app(settings, run_worker=False)
    actor = Principal("test-service", ActorType.SERVICE, frozenset({"reviewer"}), None)
    await app.state.review_service.submit(review_payload(), actor)
    job = await app.state.worker.claim_next()
    saved_first = asyncio.Event()
    original_put = app.state.storage.put_checkpoint

    async def notify_saved(*args, **kwargs):
        await original_put(*args, **kwargs)
        saved_first.set()

    app.state.storage.put_checkpoint = notify_saved

    class InterruptedModel(MockChatClient):
        counts = {"chief_blind": 0, "jury_a": 0}

        async def vote(self, role, material):
            self.counts[role] += 1
            if role == "jury_a" and self.counts[role] == 1:
                await saved_first.wait()
                raise RuntimeError("simulated interruption halfway through voting")
            return await super().vote(role, material)

    model = InterruptedModel()
    candidate = CandidateRecord(id="c1", review_id=job.id, candidate_no=1, step_index=1,
                                dimension="test_design", standardized_text="缺少预期", category="预期不明确")
    persisted = []

    async def persist(call):
        persisted.append(call["role"])

    try:
        cache = Checkpoints(app.state.storage, job, app.state.versions)
        with pytest.raises(RuntimeError, match="halfway"):
            await run_vote(job.id, [candidate], model, list(model.counts), checkpoints=cache, persist_call=persist)
        assert persisted == ["chief_blind"]
        await app.state.storage.update_job(job.id, fencing_token=job.fencing_token, status="retrying")
        reclaimed = await app.state.worker.claim_next()
        cache = Checkpoints(app.state.storage, reclaimed, app.state.versions)
        votes, calls = await run_vote(job.id, [candidate], model, list(model.counts),
                                     checkpoints=cache, persist_call=persist)
        assert model.counts == {"chief_blind": 1, "jury_a": 2}
        assert persisted == ["chief_blind", "jury_a"]
        assert len(votes) == 2 and all(c["status"] == "ok" for c in calls)
        assert "vote:c1:chief_blind" in cache.reused
    finally:
        close = getattr(app.state.storage, "close", None)
        if close:
            await close()


async def test_memory_partial_vote_recovery():
    await exercise_partial_votes(make_settings())


@pytest.mark.postgres
async def test_postgres_partial_vote_recovery(migrated_database):
    await exercise_partial_votes(make_settings(storage_backend="postgres", database_url=migrated_database))
