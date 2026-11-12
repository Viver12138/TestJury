import asyncio

from app.core.auth import Principal
from app.core.enums import ActorType
from app.main import create_app
from tests.helpers import make_settings, review_payload, valid_case


async def test_worker_pool_claims_multiple_jobs_and_stops_cleanly():
    app = create_app(make_settings(worker_concurrency=2, queue_poll_interval_ms=50), run_worker=False)
    principal = Principal("svc", ActorType.SERVICE, frozenset({"reviewer"}), "tests")
    for number in range(2):
        await app.state.review_service.submit(review_payload(valid_case(case_id=f"pool-{number}")), principal)
    entered = set()
    both = asyncio.Event()
    original = app.state.pipeline.run

    async def blocking(job, versions):
        entered.add(job.id)
        if len(entered) == 2:
            both.set()
        await asyncio.wait_for(both.wait(), timeout=2)
        return await original(job, versions)

    app.state.pipeline.run = blocking
    app.state.worker.start()
    try:
        await asyncio.wait_for(both.wait(), timeout=3)
        assert len(entered) == 2
    finally:
        await app.state.worker.stop()
    assert app.state.worker._task is None
