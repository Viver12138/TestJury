"""ACC-M0-020：阶段完成与跳过语义（跳过不算完成，两者分列）。"""

from __future__ import annotations

import pytest

from tests.helpers import auth_headers, review_payload


@pytest.mark.asyncio
async def test_skipped_arbitration_is_listed_separately(async_client, app) -> None:
    response = await async_client.post(
        "/v1/reviews", json=review_payload(), headers=auth_headers()
    )
    review_id = response.json()["review_id"]
    assert await app.state.worker.run_once() == "done"

    detail = (await async_client.get(f"/v1/reviews/{review_id}", headers=auth_headers())).json()
    completeness = detail["review_completeness"]
    assert "arbitration" not in completeness["stages_completed"]
    assert "arbitration" in completeness["stages_skipped"]
    assert completeness["complete"] is True
    # 条件未触发（无分歧）时仲裁跳过不影响 complete；不能把跳过写成完成
    stages = await app.state.storage.list_stages(review_id)
    arbitration = next(stage for stage in stages if stage.stage == "arbitration")
    assert arbitration.status == "skipped"


@pytest.mark.asyncio
async def test_required_stage_failure_is_not_counted_complete(async_client, app) -> None:
    response = await async_client.post(
        "/v1/reviews", json=review_payload(), headers=auth_headers()
    )
    review_id = response.json()["review_id"]
    await app.state.worker.run_once()

    # 模拟投票阶段失败：complete 必须为 false，且失败阶段单列
    job = await app.state.storage.get_job(review_id)
    assert job is not None
    report = dict(job.report_json or {})
    completeness = dict(report.get("review_completeness") or {})
    completeness["stages_completed"] = [
        name for name in completeness.get("stages_completed", []) if name != "vote"
    ]
    completeness["stages_failed"] = ["vote"]
    completeness["complete"] = False
    report["review_completeness"] = completeness

    from app.pipeline.stages import build_completeness

    rebuilt = build_completeness(
        {
            **{name: "succeeded" for name in completeness.get("stages_completed", [])},
            "vote": "failed",
            **{name: "skipped" for name in completeness.get("stages_skipped", [])},
        },
        raw_text=False,
        kb_covered=False,
        arbitration_required=False,
        blind="3/3",
        vote="3/3",
    )
    assert rebuilt["complete"] is False
    assert "vote" in rebuilt["stages_failed"]
