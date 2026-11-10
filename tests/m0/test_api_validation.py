"""ACC-M0-006：非法枚举与结构错误被拒绝，且不创建任务。"""

from __future__ import annotations

from tests.helpers import REVIEWER_KEY, auth_headers, review_payload, valid_case


def _submit(client, payload, key: str = REVIEWER_KEY):
    return client.post("/v1/reviews", json=payload, headers=auth_headers(key))


def test_invalid_source_is_rejected_without_creating_job(client) -> None:
    payload = review_payload(case=valid_case(source="unknown"))
    response = _submit(client, payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INPUT_INVALID"
    assert client.get("/v1/reviews", headers=auth_headers()).json()["items"] == []


def test_empty_steps_and_raw_text_is_rejected(client) -> None:
    case = valid_case(steps=[], raw_text="")
    response = _submit(client, review_payload(case=case))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INPUT_INVALID"


def test_non_contiguous_step_index_is_invalid_case(client) -> None:
    case = valid_case(
        steps=[
            {"index": 1, "action": "a", "expected": "b"},
            {"index": 3, "action": "c", "expected": "d"},
        ]
    )
    response = _submit(client, review_payload(case=case))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CASE"


def test_malformed_json_is_rejected(client) -> None:
    response = client.post(
        "/v1/reviews",
        content="{not-json",
        headers={**auth_headers(), "Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_JSON"


def test_missing_case_id_is_rejected(client) -> None:
    case = valid_case()
    case.pop("case_id")
    response = _submit(client, review_payload(case=case))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INPUT_INVALID"


def test_valid_submission_returns_202(client) -> None:
    response = _submit(client, review_payload())
    assert response.status_code == 202, response.json()
    body = response.json()
    assert body["status"] == "queued"
    assert body["generation"] == 1
    assert body["poll_url"].startswith("/v1/reviews/")


def test_case_version_defaults_to_1(client) -> None:
    case = valid_case()
    case.pop("case_version", None)
    response = _submit(client, review_payload(case=case))
    assert response.status_code == 202
    review_id = response.json()["review_id"]
    detail = client.get(f"/v1/reviews/{review_id}", headers=auth_headers()).json()
    assert detail["case_version"] == 1
