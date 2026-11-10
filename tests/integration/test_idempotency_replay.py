"""ACC-CON-001：未 force 重复提交返回真实状态（200 + idempotent_replay）。"""

from __future__ import annotations

import pytest

from tests.helpers import auth_headers, review_payload


@pytest.mark.asyncio
async def test_replay_returns_processing_state(async_client, app) -> None:
    payload = review_payload()
    first = await async_client.post("/v1/reviews", json=payload, headers=auth_headers())
    assert first.status_code == 202
    review_id = first.json()["review_id"]

    claimed = await app.state.worker.claim_next()
    assert claimed is not None and claimed.id == review_id
    assert claimed.status == "processing"

    second = await async_client.post("/v1/reviews", json=payload, headers=auth_headers())
    assert second.status_code == 200
    body = second.json()
    assert body["idempotent_replay"] is True
    assert body["review_id"] == review_id
    assert body["status"] == "processing"
    assert body["report_available"] is False
    assert "report_json" not in body

    total = await app.state.storage.list_jobs()
    assert len(total) == 1
