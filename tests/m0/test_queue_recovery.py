"""租约过期后的任务重新领取（M1 崩溃恢复最小证据）。"""

from __future__ import annotations

import asyncio

import pytest

from tests.helpers import REVIEWER_KEY, auth_headers, review_payload, valid_case


@pytest.mark.asyncio
async def test_expired_lease_is_reclaimed_with_new_fencing_token(async_client, app) -> None:
    response = await async_client.post(
        "/v1/reviews",
        json=review_payload(case=valid_case(case_id="TC-LEASE-001")),
        headers=auth_headers(REVIEWER_KEY),
    )
    assert response.status_code == 202
    review_id = response.json()["review_id"]

    first = await app.state.storage.claim_next_job(worker_id="worker-a", lease_seconds=1)
    assert first is not None and first.id == review_id
    assert first.attempt_count == 1
    assert first.fencing_token == 1

    await asyncio.sleep(1.05)

    second = await app.state.storage.claim_next_job(worker_id="worker-b", lease_seconds=30)
    assert second is not None and second.id == review_id
    assert second.attempt_count == 2
    assert second.fencing_token == 2
    assert second.locked_by == "worker-b"

    # 旧 fencing token 不能再写
    stale = await app.state.storage.heartbeat(review_id, fencing_token=1, lease_seconds=30)
    assert stale is False
