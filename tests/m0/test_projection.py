"""M1：报告 issues 投影与最终写入的 fencing 语义。"""

from __future__ import annotations

import pytest

from app.core.state_machine import FencingMismatch
from app.pipeline.projection import compare_projection, issue_id_for, records_from_report
from tests.helpers import auth_headers, review_payload, valid_case


def _case_with_issues() -> dict:
    return valid_case(
        steps=[
            {"index": 1, "action": "点击【开始挖宝】按钮", "expected": "提示已生成藏宝点"},
            {"index": 2, "action": "点击【发现】按钮"},
        ]
    )


@pytest.mark.asyncio
async def test_worker_writes_matching_projection(async_client, app) -> None:
    response = await async_client.post(
        "/v1/reviews", json=review_payload(case=_case_with_issues()), headers=auth_headers()
    )
    review_id = response.json()["review_id"]
    assert await app.state.worker.run_once() == "done"

    job = await app.state.storage.get_job(review_id)
    records = await app.state.storage.list_issues(review_id)
    assert job is not None and job.report_json is not None
    assert records
    assert compare_projection(review_id, job.report_json, records) == []
    assert [record.id for record in records] == [
        issue_id_for(review_id, record.issue_no) for record in records
    ]


@pytest.mark.asyncio
async def test_finalize_report_requires_current_fencing_token(async_client, app) -> None:
    response = await async_client.post(
        "/v1/reviews", json=review_payload(case=_case_with_issues()), headers=auth_headers()
    )
    review_id = response.json()["review_id"]
    worker_a = await app.state.storage.claim_next_job(worker_id="worker-a", lease_seconds=0)
    assert worker_a is not None
    worker_b = await app.state.storage.claim_next_job(worker_id="worker-b", lease_seconds=60)
    assert worker_b is not None and worker_b.fencing_token == worker_a.fencing_token + 1

    report = {"review_id": review_id, "issues": [], "status": "done"}
    with pytest.raises(FencingMismatch):
        await app.state.storage.finalize_report(
            review_id,
            fencing_token=worker_a.fencing_token,
            fields={"status": "done", "report_json": report, "report_locked_at": None},
            issues=records_from_report(review_id, report),
        )
    assert await app.state.storage.list_issues(review_id) == []

    await app.state.storage.finalize_report(
        review_id,
        fencing_token=worker_b.fencing_token,
        fields={"status": "done", "report_json": report},
        issues=records_from_report(review_id, report),
    )
    assert await app.state.storage.list_issues(review_id) == []
