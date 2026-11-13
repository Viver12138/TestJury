import httpx
import pytest
from pydantic import ValidationError

from app.main import create_app
from app.services.excel_import import template_workbook
from tests.helpers import make_settings


@pytest.mark.asyncio
async def test_local_excel_preview_batch_poll_report_and_replay():
    app = create_app(make_settings(local_access_without_key=True))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            data = template_workbook()
            preview = await client.post("/v1/imports/excel", files={"file": ("cases.xlsx", data)})
            assert preview.status_code == 200, preview.text
            assert await app.state.storage.list_jobs(limit=10) == []
            payload = {"cases": preview.json()["cases"]}
            created = await client.post("/v1/review-batches", json=payload)
            assert created.status_code == 202, created.text
            batch_id = created.json()["batch_id"]
            assert await app.state.worker.run_once() == "done"
            batch = (await client.get(f"/v1/review-batches/{batch_id}")).json()
            assert batch["done"] == 1 and batch["status"] == "completed"
            review_id = batch["items"][0]["review_id"]
            assert (await client.get(f"/v1/reviews/{review_id}/report")).status_code == 200
            repeat = await client.post("/v1/review-batches", json=payload)
            assert repeat.status_code == 200 and repeat.json()["batch_id"] == batch_id
            assert len(await app.state.storage.list_jobs(limit=10)) == 1
            job = await app.state.storage.get_job(review_id)
            assert job.submitter_id == "local-reviewer"
            rejected = await client.post(f"/v1/reviews/{review_id}/decisions", json={"decision": "approve"})
            assert rejected.status_code == 403
            assert (await client.post("/v1/imports/excel", files={"file": ("bad.xlsx", b"bad")})).status_code == 422
            assert len(await app.state.storage.list_jobs(limit=10)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("peer", "base", "headers", "status"), [
    ("127.0.0.1", "http://127.0.0.1", {}, 200),
    ("::1", "http://[::1]", {}, 200),
    ("10.0.0.8", "http://127.0.0.1", {"X-Forwarded-For": "127.0.0.1"}, 401),
    ("127.0.0.1", "http://127.0.0.1", {"Origin": "https://other.example"}, 403),
    ("127.0.0.1", "http://other.example", {}, 403),
    ("127.0.0.1", "http://127.0.0.1", {"Authorization": "Bearer invalid"}, 401),
])
async def test_local_access_only_allows_direct_local_requests(peer, base, headers, status):
    app = create_app(make_settings(local_access_without_key=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(peer, 123)), base_url=base) as client:
        assert (await client.get("/v1/reviews", headers=headers)).status_code == status


@pytest.mark.asyncio
async def test_auth_remains_required_by_default_and_forbidden_in_production():
    app = create_app(make_settings())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        assert (await client.post("/v1/imports/excel", files={"file": ("a.xlsx", template_workbook())})).status_code == 401
    with pytest.raises(ValidationError, match="LOCAL_ACCESS_WITHOUT_KEY"):
        make_settings(app_env="prod", local_access_without_key=True)
