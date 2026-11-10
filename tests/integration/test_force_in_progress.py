"""ACC-CON-005：运行中 force 被拒（409 REVIEW_IN_PROGRESS），终态后可新建代次。"""

from __future__ import annotations

import pytest

from tests.helpers import auth_headers, review_payload


@pytest.mark.asyncio
async def test_force_in_progress_then_after_terminal(async_client, app) -> None:
    payload = review_payload()
    first = await async_client.post("/v1/reviews", json=payload, headers=auth_headers())
    review_id = first.json()["review_id"]

    claimed = await app.state.worker.claim_next()
    assert claimed is not None and claimed.id == review_id

    forced = await async_client.post(
        "/v1/reviews",
        json=review_payload(options={"force": True}),
        headers=auth_headers(),
    )
    assert forced.status_code == 409
    assert forced.json()["error"]["code"] == "REVIEW_IN_PROGRESS"

    jobs = await app.state.storage.list_jobs(limit=10)
    assert len(jobs) == 1
    assert jobs[0].superseded_by is None

    assert await app.state.worker.execute(claimed) == "done"

    forced_again = await async_client.post(
        "/v1/reviews",
        json=review_payload(options={"force": True}),
        headers=auth_headers(),
    )
    assert forced_again.status_code == 202
    assert forced_again.json()["generation"] == 2
