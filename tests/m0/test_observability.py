"""ACC-M0-021：request_id/trace_id 贯穿与阶段指标。"""

from __future__ import annotations

import io
import json
import logging

import pytest
import structlog

from tests.helpers import auth_headers, review_payload


@pytest.mark.asyncio
async def test_stage_logs_and_metrics(async_client, app) -> None:
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
        response = await async_client.post(
            "/v1/reviews", json=review_payload(), headers=auth_headers()
        )
        review_id = response.json()["review_id"]
        assert response.headers["X-Request-Id"]
        assert await app.state.worker.run_once() == "done"
    finally:
        root.removeHandler(handler)

    records = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    stage_records = [record for record in records if record.get("event") == "review_stage"]
    assert stage_records, stream.getvalue()
    assert all(record["review_id"] == review_id for record in stage_records)
    assert {record["stage"] for record in stage_records} >= {"blind_review", "fusion", "vote", "verdict"}
    assert all("attempt" in record for record in stage_records)

    metrics = await async_client.get("/metrics")
    assert metrics.status_code == 200
    assert "testjury_stage_duration_seconds" in metrics.text
    assert "testjury_reviews_running" in metrics.text
    assert "testjury_reviews_running" in metrics.text


@pytest.mark.asyncio
async def test_request_and_trace_ids_are_propagated(async_client) -> None:
    response = await async_client.get(
        "/livez",
        headers={"X-Request-Id": "req-trace-test-1", "X-Trace-Id": "trace-test-1"},
    )
    assert response.headers["X-Request-Id"] == "req-trace-test-1"
    assert response.headers["X-Trace-Id"] == "trace-test-1"
