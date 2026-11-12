"""ACC-BIZ-006：批量入口只是多个独立单条评审，不做跨用例分析。"""

from __future__ import annotations

import pytest

from tests.helpers import auth_headers, valid_case


def _batch_payload(cases: list[dict]) -> dict:
    return {"cases": cases, "options": {"force": False}}


@pytest.mark.asyncio
async def test_batch_items_are_independent_and_partial_failure_visible(async_client, app) -> None:
    cases = [valid_case("TC-BATCH-1"), valid_case("TC-BATCH-2"), valid_case("TC-BATCH-3")]
    created = await async_client.post(
        "/v1/review-batches", json=_batch_payload(cases), headers=auth_headers()
    )
    assert created.status_code == 202, created.text
    batch_id = created.json()["batch_id"]
    assert created.json()["total"] == 3

    jobs = await app.state.storage.list_jobs(batch_id=batch_id, limit=10)
    assert len(jobs) == 3
    assert len({job.id for job in jobs}) == 3
    assert all(job.generation == 1 for job in jobs)

    # 两条执行成功，一条失败 → partially_completed，成功结果保留
    third = jobs[2]
    await app.state.storage.update_job(third.id, status="failed", error="mock failure")
    assert await app.state.worker.run_once() == "done"
    assert await app.state.worker.run_once() == "done"

    detail = (await async_client.get(f"/v1/review-batches/{batch_id}", headers=auth_headers())).json()
    assert detail["status"] == "partially_completed"
    assert detail["done"] == 2
    assert detail["failed"] == 1
    assert len(detail["items"]) == 3
    assert {item["status"] for item in detail["items"]} == {"done", "failed"}
    assert "coverage" not in detail
    assert "duplicate_analysis" not in detail


@pytest.mark.asyncio
async def test_one_invalid_test_type_rejects_whole_batch(async_client, app) -> None:
    cases = [
        valid_case("TC-OK-1"),
        valid_case("TC-BAD-1", test_type="performance"),
    ]
    response = await async_client.post(
        "/v1/review-batches", json=_batch_payload(cases), headers=auth_headers()
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_TEST_TYPE"
    assert await app.state.storage.list_jobs(limit=10) == []


@pytest.mark.asyncio
async def test_batch_over_limit_is_rejected(async_client) -> None:
    cases = [valid_case(f"TC-MANY-{index}") for index in range(51)]
    response = await async_client.post(
        "/v1/review-batches", json=_batch_payload(cases), headers=auth_headers()
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TOO_MANY_CASES"
