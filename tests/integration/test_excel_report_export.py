from io import BytesIO

import pytest
from openpyxl import load_workbook

from tests.helpers import auth_headers, valid_case


@pytest.mark.asyncio
async def test_single_and_batch_export_auth_pending_completion_and_no_model_calls(async_client, app):
    batch = await async_client.post("/v1/review-batches", headers=auth_headers(),
                                    json={"cases": [valid_case("EX-1"), valid_case("EX-2")]})
    batch_id = batch.json()["batch_id"]
    jobs = await app.state.storage.list_jobs(batch_id=batch_id, limit=10)
    single_url = f"/v1/reviews/{jobs[0].id}/report.xlsx"
    batch_url = f"/v1/review-batches/{batch_id}/report.xlsx"
    assert (await async_client.get(single_url)).status_code == 401
    assert (await async_client.get(batch_url)).status_code == 401
    assert (await async_client.get(single_url, headers=auth_headers())).status_code == 404
    pending = await async_client.get(batch_url, headers=auth_headers())
    assert pending.status_code == 200
    pending_book = load_workbook(BytesIO(pending.content))
    assert pending_book["评审汇总"]["G2"].value is None
    assert pending_book["评审汇总"].max_row == 3
    for _ in range(2):
        assert await app.state.worker.run_once() == "done"
    before = [await app.state.storage.get_job(job.id) for job in jobs]
    calls_before = [await app.state.storage.list_model_runs(job.id) for job in jobs]
    response = await async_client.get(single_url, headers=auth_headers())
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.headers["content-disposition"].endswith('.xlsx"')
    assert load_workbook(BytesIO(response.content))["评审汇总"].max_row == 2
    batch_response = await async_client.get(batch_url, headers=auth_headers())
    assert load_workbook(BytesIO(batch_response.content))["评审汇总"].max_row == 3
    assert [await app.state.storage.get_job(job.id) for job in jobs] == before
    assert [await app.state.storage.list_model_runs(job.id) for job in jobs] == calls_before
    assert (await async_client.get("/v1/review-batches/missing/report.xlsx", headers=auth_headers())).status_code == 404
    assert (await async_client.get("/v1/reviews/missing/report.xlsx", headers=auth_headers())).status_code == 404
    # Existing API clients retain their Markdown route.
    assert (await async_client.get(f"/v1/reviews/{jobs[0].id}/report", headers=auth_headers())).status_code == 200
