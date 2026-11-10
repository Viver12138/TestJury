"""ACC-M0-001：服务启动、存活探针与统一错误 envelope、JSON 日志。"""

from __future__ import annotations

import io
import json
import logging

import structlog

from tests.helpers import auth_headers


def test_livez_returns_ok(client) -> None:
    response = client.get("/livez")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_unknown_route_uses_error_envelope_with_request_id(client) -> None:
    response = client.get("/v1/not-exist")
    assert response.status_code == 404
    payload = response.json()
    error = payload["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["retryable"] is False
    assert error["request_id"]
    assert response.headers["X-Request-Id"] == error["request_id"]


def test_request_id_header_is_echoed(client) -> None:
    response = client.get("/livez", headers={"X-Request-Id": "req-custom-123"})
    assert response.headers["X-Request-Id"] == "req-custom-123"


def test_access_log_is_json_and_links_request_id(client) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(ensure_ascii=False)
        )
    )
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        response = client.get("/livez")
    finally:
        root.removeHandler(handler)

    records = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    access = [record for record in records if record.get("event") == "http_request"]
    assert access, stream.getvalue()
    match = [record for record in access if record.get("request_id") == response.headers["X-Request-Id"]]
    assert match, access
    assert match[0]["method"] == "GET"
    assert match[0]["status"] == 200


def test_unauthorized_has_envelope(client) -> None:
    response = client.get("/v1/reviews")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_authenticated_request_succeeds(client) -> None:
    response = client.get("/v1/reviews", headers=auth_headers())
    assert response.status_code == 200
    assert response.json() == {"items": []}
