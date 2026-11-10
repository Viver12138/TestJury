"""ACC-M0-015：审批人与提交人分离（同一身份提交并审批必须被拒）。"""

from __future__ import annotations

import pytest

from tests.helpers import APPROVER_KEY, auth_headers, review_payload


@pytest.mark.asyncio
async def test_self_approval_is_rejected_and_audited(async_client, app) -> None:
    response = await async_client.post(
        "/v1/reviews", json=review_payload(), headers=auth_headers(APPROVER_KEY)
    )
    assert response.status_code == 202
    review_id = response.json()["review_id"]
    assert await app.state.worker.run_once() == "done"

    decision = await async_client.post(
        f"/v1/reviews/{review_id}/decisions",
        json={"decision": "approve"},
        headers=auth_headers(APPROVER_KEY),
    )
    assert decision.status_code == 403
    assert decision.json()["error"]["code"] == "FORBIDDEN"

    audit = await app.state.storage.list_audit(review_id=review_id)
    assert any(record.event_type == "decision_rejected" for record in audit)


@pytest.mark.asyncio
async def test_other_approver_can_approve_without_changing_ai_verdict(async_client, app) -> None:
    response = await async_client.post(
        "/v1/reviews", json=review_payload(), headers=auth_headers()
    )
    review_id = response.json()["review_id"]
    assert await app.state.worker.run_once() == "done"
    before = (await async_client.get(f"/v1/reviews/{review_id}", headers=auth_headers())).json()

    decision = await async_client.post(
        f"/v1/reviews/{review_id}/decisions",
        json={"decision": "approve"},
        headers=auth_headers(APPROVER_KEY),
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["human_status"] == "approved"

    after = (await async_client.get(f"/v1/reviews/{review_id}", headers=auth_headers())).json()
    assert after["human_status"] == "approved"
    assert after["ai_verdict"] == before["ai_verdict"]
    assert after["report"]["ai_verdict"] == before["report"]["ai_verdict"]


@pytest.mark.asyncio
async def test_reject_requires_reason(async_client, app) -> None:
    response = await async_client.post(
        "/v1/reviews", json=review_payload(), headers=auth_headers()
    )
    review_id = response.json()["review_id"]
    await app.state.worker.run_once()

    decision = await async_client.post(
        f"/v1/reviews/{review_id}/decisions",
        json={"decision": "reject"},
        headers=auth_headers(APPROVER_KEY),
    )
    assert decision.status_code == 422
    assert decision.json()["error"]["code"] == "INVALID_DECISION"
