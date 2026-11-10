"""ACC-M0-023：系统身份与人工审批身份分离。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.enums import ActorType
from tests.helpers import APPROVER_KEY, REVOKED_KEY, SERVICE_KEY, auth_headers


def test_service_identity_cannot_approve(client) -> None:
    response = client.post(
        "/v1/reviews/r-1/decisions",
        json={"decision": "approve"},
        headers=auth_headers(SERVICE_KEY),
    )
    assert response.status_code == 403
    assert "系统身份" in response.json()["error"]["message"]


def test_revoked_key_is_unauthorized(client, app) -> None:
    app.state.auth_repository.add_key(
        REVOKED_KEY,
        actor_id="revoked-user",
        roles=["reviewer"],
        revoked_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    response = client.get("/v1/reviews", headers=auth_headers(REVOKED_KEY))
    assert response.status_code == 401


def test_expired_key_is_unauthorized(client, app) -> None:
    expired_key = "expired-key-0007"
    app.state.auth_repository.add_key(
        expired_key,
        actor_id="expired-user",
        roles=["reviewer"],
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    response = client.get("/v1/reviews", headers=auth_headers(expired_key))
    assert response.status_code == 401


def test_human_approver_identity_reaches_business_layer(client) -> None:
    response = client.post(
        "/v1/reviews/not-there/decisions",
        json={"decision": "approve"},
        headers=auth_headers(APPROVER_KEY),
    )
    assert response.status_code == 404


def test_principal_actor_type_comes_from_authorization_table(client, app) -> None:
    # reviewer-1 是 human；svc-1 是 service。角色相同也不能互换身份类型。
    reviewer = app.state.auth_repository._records  # 仅测试检查授权表内容
    hashes = {record.actor_id: record.actor_type for record in reviewer.values()}
    assert hashes["reviewer-1"] == ActorType.HUMAN.value
    assert hashes["svc-1"] == ActorType.SERVICE.value
