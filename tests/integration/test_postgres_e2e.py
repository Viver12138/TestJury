"""PostgreSQL 存储适配器全链路（Mock 模型）：提交→执行→报告→审批。"""

from __future__ import annotations

import httpx
import pytest

from app.main import create_app
from tests.helpers import APPROVER_KEY, auth_headers, make_settings, review_payload, valid_case
from tests.pg import dsn


def _async_url() -> str:
    url = dsn()
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture()
def pg_app(migrated_database: str):
    settings = make_settings(
        database_url=_async_url(),
        storage_backend="postgres",
        run_worker=False,
    )
    app = create_app(settings, run_worker=False)
    return app


@pytest.mark.asyncio
async def test_postgres_full_chain(pg_app) -> None:
    async with pg_app.router.lifespan_context(pg_app):
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            case = valid_case(
                steps=[
                    {"index": 1, "action": "点击【开始挖宝】按钮", "expected": "提示已生成藏宝点"},
                    {"index": 2, "action": "点击【发现】按钮"},
                ]
            )
            created = await client.post(
                "/v1/reviews", json=review_payload(case=case), headers=auth_headers()
            )
            assert created.status_code == 202, created.text
            review_id = created.json()["review_id"]

            replay = await client.post(
                "/v1/reviews", json=review_payload(case=case), headers=auth_headers()
            )
            assert replay.status_code == 200
            assert replay.json()["review_id"] == review_id

            assert await pg_app.state.worker.run_once() == "done"

            detail = (await client.get(f"/v1/reviews/{review_id}", headers=auth_headers())).json()
            assert detail["status"] == "done"
            assert detail["report"]["issues"]
            assert detail["review_completeness"]["complete"] is True

            stages = await pg_app.state.storage.list_stages(review_id)
            assert {stage.stage for stage in stages} >= {"input_check", "blind_review", "verdict"}
            votes = await pg_app.state.storage.list_votes(review_id)
            assert votes and all(vote.validity == "accept" for vote in votes)
            candidates = await pg_app.state.storage.list_candidates(review_id)
            assert candidates

            decision = await client.post(
                f"/v1/reviews/{review_id}/decisions",
                json={"decision": "approve"},
                headers=auth_headers(APPROVER_KEY),
            )
            assert decision.status_code == 200, decision.text
            decisions = await pg_app.state.storage.list_decisions(review_id)
            assert len(decisions) == 1
            assert decisions[0].decision == "approve"

            job = await pg_app.state.storage.get_job(review_id)
            assert job is not None and job.human_status == "approved"
