"""ACC-M0-014：API Key 角色映射与伪造 X-Role 拒绝。"""

from __future__ import annotations

from tests.helpers import ADMIN_KEY, APPROVER_KEY, REVIEWER_KEY, auth_headers


def _decision_body() -> dict:
    return {"decision": "approve"}


def test_reviewer_cannot_approve(client) -> None:
    response = client.post(
        "/v1/reviews/r-1/decisions",
        json=_decision_body(),
        headers=auth_headers(REVIEWER_KEY),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_forged_x_role_does_not_elevate(client) -> None:
    headers = {**auth_headers(REVIEWER_KEY), "X-Role": "admin"}
    response = client.post("/v1/reviews/r-1/decisions", json=_decision_body(), headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_admin_is_not_approver(client) -> None:
    response = client.post(
        "/v1/reviews/r-1/decisions",
        json=_decision_body(),
        headers=auth_headers(ADMIN_KEY),
    )
    assert response.status_code == 403


def test_missing_key_is_401(client) -> None:
    response = client.post("/v1/reviews/r-1/decisions", json=_decision_body())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_unknown_key_is_401(client) -> None:
    response = client.get("/v1/reviews", headers=auth_headers("not-a-real-key"))
    assert response.status_code == 401


def test_approver_passes_authorization_but_report_missing(client) -> None:
    response = client.post(
        "/v1/reviews/r-missing/decisions",
        json=_decision_body(),
        headers=auth_headers(APPROVER_KEY),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_reviewer_can_request_changes_by_role(client) -> None:
    response = client.post(
        "/v1/reviews/r-missing/decisions",
        json={"decision": "request_changes", "reason": "补充预期"},
        headers=auth_headers(REVIEWER_KEY),
    )
    # 角色允许，但报告不存在 → 404
    assert response.status_code == 404
