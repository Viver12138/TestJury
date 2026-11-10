"""ACC-CON-011：幂等作用范围与保留策略（逐接口语义）。"""

from __future__ import annotations

import pytest

from tests.helpers import ADMIN_KEY, APPROVER_KEY, auth_headers, review_payload, valid_case


@pytest.mark.asyncio
async def test_review_repeat_is_idempotent(async_client) -> None:
    payload = review_payload()
    first = await async_client.post("/v1/reviews", json=payload, headers=auth_headers())
    second = await async_client.post("/v1/reviews", json=payload, headers=auth_headers())
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["idempotent_replay"] is True
    assert second.json()["review_id"] == first.json()["review_id"]


@pytest.mark.asyncio
async def test_batch_repeat_returns_same_batch(async_client) -> None:
    payload = {
        "cases": [valid_case("TC-B1"), valid_case("TC-B2")],
        "options": {"force": False},
    }
    first = await async_client.post("/v1/review-batches", json=payload, headers=auth_headers())
    second = await async_client.post("/v1/review-batches", json=payload, headers=auth_headers())
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["batch_id"] == first.json()["batch_id"]


@pytest.mark.asyncio
async def test_attachment_deduplicates_by_sha256(async_client) -> None:
    content = b"fake-png-bytes-001"
    first = await async_client.post(
        "/v1/attachments",
        files={"file": ("step3.png", content, "image/png")},
        headers=auth_headers(),
    )
    second = await async_client.post(
        "/v1/attachments",
        files={"file": ("renamed.png", content, "image/png")},
        headers=auth_headers(),
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200
    assert first.json()["attachment_id"] == second.json()["attachment_id"]
    assert first.json()["sha256"] == second.json()["sha256"]


@pytest.mark.asyncio
async def test_decision_repeat_conflicts(async_client, app) -> None:
    response = await async_client.post(
        "/v1/reviews", json=review_payload(), headers=auth_headers()
    )
    review_id = response.json()["review_id"]
    await app.state.worker.run_once()

    first = await async_client.post(
        f"/v1/reviews/{review_id}/decisions",
        json={"decision": "approve"},
        headers=auth_headers(APPROVER_KEY),
    )
    assert first.status_code == 200
    second = await async_client.post(
        f"/v1/reviews/{review_id}/decisions",
        json={"decision": "approve"},
        headers=auth_headers(APPROVER_KEY),
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DECISION_CONFLICT"


@pytest.mark.asyncio
async def test_deleted_review_allows_new_task(async_client, app) -> None:
    payload = review_payload()
    first = await async_client.post("/v1/reviews", json=payload, headers=auth_headers())
    review_id = first.json()["review_id"]
    await app.state.worker.run_once()

    deleted = await async_client.delete(
        f"/v1/reviews/{review_id}", headers=auth_headers(ADMIN_KEY)
    )
    assert deleted.status_code == 204

    again = await async_client.post("/v1/reviews", json=payload, headers=auth_headers())
    assert again.status_code == 202
    assert again.json()["review_id"] != review_id
