"""ACC-BIZ-001..004：业务范围与职责边界。"""

from __future__ import annotations

import httpx
import pytest

from app.main import create_app
from tests.helpers import (
    COMPAT_KEY,
    REVIEWER_KEY,
    auth_headers,
    make_settings,
    review_payload,
    valid_case,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_type",
    ["performance", "security", "compatibility", "reliability", "usability", "other"],
)
async def test_non_functional_test_types_are_rejected(async_client, test_type: str) -> None:
    payload = review_payload(case=valid_case(test_type=test_type))
    response = await async_client.post("/v1/reviews", json=payload, headers=auth_headers())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_TEST_TYPE"
    assert "functional" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_no_job_created_for_rejected_types(async_client) -> None:
    payload = review_payload(case=valid_case(test_type="performance"))
    await async_client.post("/v1/reviews", json=payload, headers=auth_headers())
    listing = await async_client.get("/v1/reviews", headers=auth_headers())
    assert listing.json()["items"] == []


@pytest.mark.asyncio
async def test_missing_test_type_in_strict_mode_is_rejected(async_client) -> None:
    case = valid_case()
    case.pop("test_type")
    response = await async_client.post(
        "/v1/reviews", json=review_payload(case=case), headers=auth_headers()
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TEST_TYPE_REQUIRED"


@pytest.mark.asyncio
async def test_unknown_test_type_is_input_invalid(async_client) -> None:
    response = await async_client.post(
        "/v1/reviews",
        json=review_payload(case=valid_case(test_type="unknown")),
        headers=auth_headers(),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INPUT_INVALID"


@pytest.mark.asyncio
async def test_compat_mode_only_for_whitelisted_caller() -> None:
    app = create_app(
        make_settings(
            test_type_default_policy="compat",
            test_type_compat_callers="caller-compat",
        ),
        run_worker=False,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            case = valid_case()
            case.pop("test_type")
            allowed = await client.post(
                "/v1/reviews",
                json=review_payload(case=case),
                headers=auth_headers(COMPAT_KEY),
            )
            assert allowed.status_code == 202, allowed.text
            review_id = allowed.json()["review_id"]
            detail = (
                await client.get(f"/v1/reviews/{review_id}", headers=auth_headers(COMPAT_KEY))
            ).json()
            assert detail["test_type"] == "functional"
            assert detail["test_type_source"] == "compat_default"

            denied = await client.post(
                "/v1/reviews",
                json=review_payload(case=case),
                headers=auth_headers(REVIEWER_KEY),
            )
            assert denied.status_code == 422
            assert denied.json()["error"]["code"] == "TEST_TYPE_REQUIRED"


@pytest.mark.asyncio
async def test_ai_verdict_never_expresses_approval(async_client, app) -> None:
    response = await async_client.post(
        "/v1/reviews", json=review_payload(), headers=auth_headers()
    )
    review_id = response.json()["review_id"]
    assert await app.state.worker.run_once() == "done"

    detail = (await async_client.get(f"/v1/reviews/{review_id}", headers=auth_headers())).json()
    assert detail["ai_verdict"] in ("conditional", "need_human", None)
    assert detail["ai_verdict"] != "approved"

    from tests.helpers import APPROVER_KEY

    approved = await async_client.post(
        f"/v1/reviews/{review_id}/decisions",
        json={"decision": "approve"},
        headers=auth_headers(APPROVER_KEY),
    )
    assert approved.status_code == 200
    after = (await async_client.get(f"/v1/reviews/{review_id}", headers=auth_headers())).json()
    assert after["human_status"] == "approved"
    assert after["ai_verdict"] == detail["ai_verdict"]

    markdown = await async_client.get(
        f"/v1/reviews/{review_id}/report", headers=auth_headers()
    )
    assert "用例通过" not in markdown.text
    assert "审批通过" not in markdown.text


@pytest.mark.asyncio
async def test_information_limits_are_visible(async_client, app) -> None:
    case = valid_case()
    payload = {"case": case, "options": {"force": False}}
    response = await async_client.post("/v1/reviews", json=payload, headers=auth_headers())
    assert response.status_code == 202
    review_id = response.json()["review_id"]
    await app.state.worker.run_once()

    detail = (await async_client.get(f"/v1/reviews/{review_id}", headers=auth_headers())).json()
    reasons = set(detail["degraded_reasons"])
    assert {"scope_missing", "automation_context_missing"} <= reasons
    assert detail["report"]["issues"] == [] or all(
        issue["severity"] != "blocker" for issue in detail["report"]["issues"]
    )
