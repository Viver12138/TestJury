import httpx
import pytest

from app.main import create_app
from app.storage.models import new_id
from tests.helpers import auth_headers, make_settings, review_payload, valid_case


async def exercise_admission(settings):
    # Build only the Mock adapter; enable the live admission policy after startup.
    app = create_app(settings, run_worker=False)
    async with app.router.lifespan_context(app):
        settings.review_model_mode = "live"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                    headers=auth_headers()) as client:
            first = review_payload(valid_case(case_id="budget-existing"))
            response = await client.post("/v1/reviews", json=first)
            assert response.status_code == 202
            review_id = response.json()["review_id"]
            old_batch = {"cases": [valid_case(case_id="existing-batch-child")]}
            assert (await client.post("/v1/review-batches", json=old_batch)).status_code == 202
            job = await app.state.worker.claim_next()
            reservation = {"id": new_id(), "model": "test", "tokens_reserved": 100, "cost_reserved": 1.0}
            limits = {"review_tokens": 1000, "review_cost": 2, "daily_cost": 1, "batch_cost": 10}
            assert await app.state.storage.reserve_model_budget(job.id, job.fencing_token, reservation, limits)
            response = await client.post("/v1/reviews", json=review_payload(valid_case(case_id="blocked-new")))
            assert response.status_code == 429 and response.json()["error"]["code"] == "BUDGET_EXCEEDED"
            assert (await client.post("/v1/reviews", json=first)).status_code == 200
            assert (await client.post("/v1/review-batches", json=old_batch)).status_code == 200
            assert len(await app.state.storage.list_jobs()) == 2
            # Refusing a forced generation must not supersede the existing result.
            await app.state.storage.update_job(review_id, status="done")
            response = await client.post("/v1/reviews", json={**first, "options": {"force": True}})
            assert response.status_code == 429
            assert (await app.state.storage.get_job(review_id)).superseded_by is None
            # Refuse a new batch before creating a batch or children. It is new (202)
            # when capacity later becomes available, never an orphan replay (200).
            new_batch = {"cases": [valid_case(case_id="blocked-batch-child")]}
            assert (await client.post("/v1/review-batches", json=new_batch)).status_code == 429
            await app.state.storage.settle_model_budget(reservation["id"], 50, 0.1)
            assert (await client.post("/v1/review-batches", json=new_batch)).status_code == 202
            assert len(await app.state.storage.list_jobs()) == 3


async def test_memory_daily_admission_preserves_replays_and_rejects_without_partial_writes():
    await exercise_admission(make_settings(daily_budget_cost=1))


@pytest.mark.postgres
async def test_postgres_daily_admission_preserves_replays_and_rejects_without_partial_writes(migrated_database):
    await exercise_admission(make_settings(daily_budget_cost=1, storage_backend="postgres",
                                          database_url=migrated_database))


async def exercise_batch_admission(settings):
    app = create_app(settings, run_worker=False)
    async with app.router.lifespan_context(app):
        settings.review_model_mode = "live"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                    headers=auth_headers()) as client:
            payload = {"cases": [valid_case(case_id="batch-exhausted")]}
            response = await client.post("/v1/review-batches", json=payload)
            assert response.status_code == 202
            batch_id = response.json()["batch_id"]
            job = await app.state.worker.claim_next()
            reservation = {"id": new_id(), "model": "test", "tokens_reserved": 100, "cost_reserved": 1.0}
            limits = {"review_tokens": 1000, "review_cost": 2, "daily_cost": 10, "batch_cost": 1}
            assert await app.state.storage.reserve_model_budget(job.id, job.fencing_token, reservation, limits)
            await app.state.storage.update_job(job.id, status="failed")
            assert (await client.post("/v1/review-batches", json=payload)).status_code == 200
            response = await client.post("/v1/review-batches", json={**payload, "options": {"force": True}})
            assert response.status_code == 429
            assert response.json()["error"]["details"]["scope"] == "batch"
            assert len(await app.state.storage.list_jobs(batch_id=batch_id)) == 1
            assert (await app.state.storage.get_job(job.id)).superseded_by is None
            # Another batch has its own allowance while the daily limit still permits it.
            response = await client.post("/v1/review-batches", json={"cases": [valid_case(case_id="another-batch")]})
            assert response.status_code == 202


async def test_memory_batch_admission_preserves_replay_but_blocks_forced_spend():
    await exercise_batch_admission(make_settings(daily_budget_cost=10, batch_budget_cost=1))


@pytest.mark.postgres
async def test_postgres_batch_admission_preserves_replay_but_blocks_forced_spend(migrated_database):
    await exercise_batch_admission(make_settings(daily_budget_cost=10, batch_budget_cost=1, storage_backend="postgres",
                                                database_url=migrated_database))
