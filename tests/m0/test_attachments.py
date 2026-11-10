"""M1：附件绑定评审（上传 → 引用校验 → 报告展示 → 删除语义）。"""

from __future__ import annotations

import pytest

from tests.helpers import ADMIN_KEY, REVIEWER2_KEY, auth_headers, review_payload, valid_case


async def _upload(client, content: bytes, *, key: str | None = None) -> dict:
    headers = auth_headers(key) if key else auth_headers()
    response = await client.post(
        "/v1/attachments",
        files={"file": ("step3.png", content, "image/png")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _case_with_attachment(attachment: dict, case_id: str = "TC-ATT-1") -> dict:
    return valid_case(
        case_id=case_id,
        attachments=[
            {
                "attachment_id": attachment["attachment_id"],
                "file_name": attachment["file_name"],
                "sha256": attachment["sha256"],
            }
        ],
    )


@pytest.mark.asyncio
async def test_attachment_is_bound_and_visible_but_not_analyzed(async_client, app) -> None:
    attachment = await _upload(async_client, b"attachment-content-1")
    response = await async_client.post(
        "/v1/reviews",
        json=review_payload(case=_case_with_attachment(attachment)),
        headers=auth_headers(),
    )
    assert response.status_code == 202, response.text
    review_id = response.json()["review_id"]
    assert await app.state.worker.run_once() == "done"

    detail = (await async_client.get(f"/v1/reviews/{review_id}", headers=auth_headers())).json()
    items = detail["report"]["attachments"]
    assert len(items) == 1
    assert items[0]["attachment_id"] == attachment["attachment_id"]
    assert items[0]["analyzed_by_ai"] is False

    bindings = await app.state.storage.list_review_attachments(review_id)
    assert [record.id for record in bindings] == [attachment["attachment_id"]]

    markdown = await async_client.get(
        f"/v1/reviews/{review_id}/report", headers=auth_headers()
    )
    assert "附件仅存档，未发送给模型分析" in markdown.text


@pytest.mark.asyncio
async def test_sha_mismatch_is_rejected(async_client) -> None:
    attachment = await _upload(async_client, b"attachment-content-2")
    case = _case_with_attachment(attachment)
    case["attachments"][0]["sha256"] = "0" * 64
    response = await async_client.post(
        "/v1/reviews", json=review_payload(case=case), headers=auth_headers()
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INPUT_INVALID"


@pytest.mark.asyncio
async def test_unknown_attachment_is_rejected(async_client) -> None:
    case = valid_case(
        attachments=[
            {
                "attachment_id": "00000000-0000-0000-0000-000000000000",
                "file_name": "missing.png",
                "sha256": "1" * 64,
            }
        ]
    )
    response = await async_client.post(
        "/v1/reviews", json=review_payload(case=case), headers=auth_headers()
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INPUT_INVALID"


@pytest.mark.asyncio
async def test_other_callers_attachment_is_forbidden(async_client) -> None:
    attachment = await _upload(async_client, b"attachment-content-3")
    response = await async_client.post(
        "/v1/reviews",
        json=review_payload(case=_case_with_attachment(attachment)),
        headers=auth_headers(REVIEWER2_KEY),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_attachment_content_changes_input_hash(async_client, app) -> None:
    first = await _upload(async_client, b"attachment-content-4")
    second = await _upload(async_client, b"attachment-content-5")

    first_response = await async_client.post(
        "/v1/reviews",
        json=review_payload(case=_case_with_attachment(first, "TC-ATT-HASH")),
        headers=auth_headers(),
    )
    second_response = await async_client.post(
        "/v1/reviews",
        json=review_payload(case=_case_with_attachment(second, "TC-ATT-HASH")),
        headers=auth_headers(),
    )
    assert first_response.status_code == 202
    assert second_response.status_code == 202
    job_a = await app.state.storage.get_job(first_response.json()["review_id"])
    job_b = await app.state.storage.get_job(second_response.json()["review_id"])
    assert job_a is not None and job_b is not None
    assert job_a.idempotency_key != job_b.idempotency_key
    assert job_a.input_hash != job_b.input_hash


@pytest.mark.asyncio
async def test_deleting_review_clears_bindings(async_client, app) -> None:
    attachment = await _upload(async_client, b"attachment-content-6")
    response = await async_client.post(
        "/v1/reviews",
        json=review_payload(case=_case_with_attachment(attachment)),
        headers=auth_headers(),
    )
    review_id = response.json()["review_id"]
    assert await app.state.storage.list_review_attachments(review_id)

    deleted = await async_client.delete(
        f"/v1/reviews/{review_id}", headers=auth_headers(ADMIN_KEY)
    )
    assert deleted.status_code == 204
    assert await app.state.storage.list_review_attachments(review_id) == []
