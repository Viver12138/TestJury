"""Mock 全链路冒烟：提交 → 领取 → 阶段 → 结论 → 报告（M0 基础链路）。"""

from __future__ import annotations

import pytest

from tests.helpers import REVIEWER_KEY, auth_headers, review_payload, valid_case


@pytest.mark.asyncio
async def test_mock_pipeline_produces_valid_report(async_client, app) -> None:
    case = valid_case(
        steps=[
            {"index": 1, "action": "点击【开始挖宝】按钮", "expected": "界面提示已生成藏宝点"},
            {"index": 2, "action": "传送到洛阳藏宝点坐标 (312, 480)", "expected": "角色到达藏宝点范围"},
            {"index": 3, "action": "点击【发现】按钮"},
        ]
    )
    response = await async_client.post(
        "/v1/reviews", json=review_payload(case=case), headers=auth_headers(REVIEWER_KEY)
    )
    assert response.status_code == 202, response.text
    review_id = response.json()["review_id"]

    queue = await app.state.storage.queue_depth()
    assert queue == 1

    terminal = await app.state.worker.run_once()
    assert terminal == "done", terminal

    detail = (await async_client.get(f"/v1/reviews/{review_id}", headers=auth_headers())).json()
    assert detail["status"] == "done"
    assert detail["ai_verdict"] in ("blocked", "conditional", "need_human")
    assert detail["review_completeness"]["complete"] is True
    assert detail["review_completeness"]["stages_completed"]
    assert detail["report_available"] is True

    report = detail["report"]
    assert report["review_id"] == review_id
    assert report["report_schema_version"] == "report-1.0"
    assert report["issues"]
    assert report["summary"]["total_issues"] == len(report["issues"])

    markdown = await async_client.get(
        f"/v1/reviews/{review_id}/report", headers=auth_headers()
    )
    assert markdown.status_code == 200
    assert "评审报告" in markdown.text
    assert "用例通过" not in markdown.text
