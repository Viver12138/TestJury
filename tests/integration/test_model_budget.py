import asyncio

import pytest

from app.core.auth import Principal
from app.core.budget import ModelBudget, active_budget
from app.core.enums import ActorType
from app.llm.base import AdapterError, ChatMessage, ChatRequest, VoteDecision
from app.llm.mock import MockChatClient
from app.main import create_app
from app.storage.models import ReviewTaskRecord, new_id
from tests.helpers import make_settings, review_payload, valid_case
from tests.unit.test_chat_review_model import _model


async def exercise_shared_budget(settings):
    app = create_app(settings, run_worker=False)
    actor = Principal("budget-test", ActorType.SERVICE, frozenset({"reviewer"}), None)
    jobs = []
    try:
        for i in range(2):
            await app.state.review_service.submit(review_payload(valid_case(case_id=f"budget-{i}")), actor)
            jobs.append(await app.state.worker.claim_next())
        limits = {"review_tokens": 1000, "review_cost": 2.0, "batch_cost": 3.0, "daily_cost": 1.5}
        rows = [{"id": new_id(), "model": "test", "tokens_reserved": 400, "cost_reserved": 1.0} for _ in jobs]
        results = await asyncio.gather(*(app.state.storage.reserve_model_budget(j.id, j.fencing_token, r, limits)
                                         for j, r in zip(jobs, rows, strict=True)))
        assert sorted(results) == [False, True]
        winner = results.index(True)
        # Unknown charge remains reserved until actual usage arrives. Settling is idempotent.
        await app.state.storage.settle_model_budget(rows[winner]["id"], 100, 0.2)
        await app.state.storage.settle_model_budget(rows[winner]["id"], 1, 0.0)
        assert float((await app.state.storage.list_model_budget(jobs[winner].id))[0]["cost_actual"]) == 0.2
        loser = 1 - winner
        assert await app.state.storage.reserve_model_budget(jobs[loser].id, jobs[loser].fencing_token, rows[loser], limits)
        # A new worker object sees the durable daily reservation and cannot bypass it.
        extra = {**rows[winner], "id": new_id()}
        assert not await app.state.storage.reserve_model_budget(jobs[winner].id, jobs[winner].fencing_token, extra, limits)
    finally:
        close = getattr(app.state.storage, "close", None)
        if close:
            await close()


async def test_memory_budget_serializes_parallel_reservations():
    await exercise_shared_budget(make_settings())


@pytest.mark.postgres
async def test_postgres_budget_serializes_parallel_reservations(migrated_database):
    await exercise_shared_budget(make_settings(storage_backend="postgres", database_url=migrated_database))


async def test_exhausted_budget_sends_no_provider_request():
    settings = make_settings(review_budget_tokens=1)
    app = create_app(settings, run_worker=False)
    actor = Principal("budget-test", ActorType.SERVICE, frozenset({"reviewer"}), None)
    await app.state.review_service.submit(review_payload(), actor)
    job = await app.state.worker.claim_next()
    budget = ModelBudget(app.state.storage, job, settings)
    token = active_budget.set(budget)
    model, adapter = _model('{}')
    try:
        with pytest.raises(AdapterError, match="BUDGET_EXCEEDED"):
            await model._complete("chief_blind", ChatRequest(messages=[ChatMessage("user", "测试")], max_tokens=10))
        assert adapter.requests == []
        assert budget.exhausted
    finally:
        active_budget.reset(token)


async def test_budget_failure_is_reported_as_budget_failure():
    settings = make_settings(review_budget_tokens=1)
    app = create_app(settings, run_worker=False)
    model, adapter = _model('{}')
    app.state.pipeline.model = model
    actor = Principal("budget-test", ActorType.SERVICE, frozenset({"reviewer"}), None)
    submitted = await app.state.review_service.submit(review_payload(), actor)
    assert await app.state.worker.run_once() == "failed"
    job = await app.state.storage.get_job(submitted.body["review_id"])
    assert job.error == "budget_exceeded"
    assert adapter.requests == []


@pytest.mark.postgres
async def test_batch_budget_and_review_tasks_work_with_real_database(migrated_database):
    app = create_app(make_settings(storage_backend="postgres", database_url=migrated_database), run_worker=False)
    actor = Principal("budget-test", ActorType.SERVICE, frozenset({"reviewer"}), None)
    try:
        _, result = await app.state.batch_service.create({"cases": [valid_case(case_id="batch-budget-1"),
                                                                  valid_case(case_id="batch-budget-2")]}, actor)
        jobs = [await app.state.worker.claim_next(), await app.state.worker.claim_next()]
        assert all(j.batch_id == result["batch_id"] for j in jobs)
        limits = {"review_tokens": 1000, "review_cost": 5, "batch_cost": 1, "daily_cost": 100}
        reservations = [{"id": new_id(), "model": "test", "tokens_reserved": 100, "cost_reserved": 0.6} for _ in jobs]
        accepted = await asyncio.gather(*(app.state.storage.reserve_model_budget(j.id, j.fencing_token, r, limits)
                                          for j, r in zip(jobs, reservations, strict=True)))
        assert sorted(accepted) == [False, True]

        class UncertainModel(MockChatClient):
            async def vote(self, role, material):
                return VoteDecision("not_assessed", reason="测试分歧")

        app.state.pipeline.model = UncertainModel()
        missing = valid_case(case_id="pending-review-task", steps=[{"index": 1, "action": "提交", "expected": None}])
        submitted = await app.state.review_service.submit(review_payload(missing), actor)
        assert await app.state.worker.run_once() in {"done", "completed_with_warnings"}
        tasks = [t for t in await app.state.storage.list_review_tasks() if t.review_id == submitted.body["review_id"]]
        assert tasks
        assert tasks[0].issue_id in {i.id for i in await app.state.storage.list_issues(submitted.body["review_id"])}
    finally:
        await app.state.storage.close()


@pytest.mark.postgres
async def test_report_finalization_rolls_back_when_review_task_insert_fails(migrated_database):
    app = create_app(make_settings(storage_backend="postgres", database_url=migrated_database), run_worker=False)
    actor = Principal("rollback-test", ActorType.SERVICE, frozenset({"reviewer"}), None)
    try:
        await app.state.review_service.submit(review_payload(), actor)
        job = await app.state.worker.claim_next()
        with pytest.raises(ValueError):
            await app.state.storage.finalize_report(
                job.id, fencing_token=job.fencing_token,
                fields={"status": "done", "report_json": {"issues": []}}, issues=[],
                review_tasks=[ReviewTaskRecord(id=new_id(), review_id=job.id, review_level="report"),
                              ReviewTaskRecord(id="invalid-uuid", review_id=job.id, review_level="report")])
        current = await app.state.storage.get_job(job.id)
        assert current.status == "processing" and current.report_json is None
        assert await app.state.storage.list_review_tasks() == []
    finally:
        await app.state.storage.close()
