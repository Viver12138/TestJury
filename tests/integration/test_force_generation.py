"""ACC-CON-002：force 形成新代次，旧记录被单向取代，历史不可变。"""

from __future__ import annotations

import copy

import pytest

from tests.helpers import auth_headers, review_payload


@pytest.mark.asyncio
async def test_force_creates_new_generation(async_client, app) -> None:
    payload = review_payload()
    first = await async_client.post("/v1/reviews", json=payload, headers=auth_headers())
    old_id = first.json()["review_id"]
    assert await app.state.worker.run_once() == "done"
    old_job = await app.state.storage.get_job(old_id)
    old_report = copy.deepcopy(old_job.report_json)

    forced = await async_client.post(
        "/v1/reviews",
        json=review_payload(options={"force": True}),
        headers=auth_headers(),
    )
    assert forced.status_code == 202, forced.text
    new_id = forced.json()["review_id"]
    assert new_id != old_id
    assert forced.json()["generation"] == 2

    new_job = await app.state.storage.get_job(new_id)
    old_after = await app.state.storage.get_job(old_id)
    assert new_job is not None and old_after is not None
    assert new_job.generation == 2
    assert new_job.parent_review_id == old_id
    assert old_after.superseded_by == new_id
    assert old_after.report_json == old_report
    assert old_after.status == "done"
