"""M1：PostgreSQL 投影重建脚本与一致性检查（损坏投影可被发现并修复）。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from app.main import create_app
from tests.helpers import auth_headers, make_settings, review_payload, valid_case
from tests.pg import dsn

REPO_ROOT = Path(__file__).resolve().parents[2]


def _async_url() -> str:
    return dsn().replace("postgresql://", "postgresql+asyncpg://", 1)


def _run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["DATABASE_URL"] = dsn()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / name), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )


@pytest.fixture()
def pg_app(migrated_database: str):
    settings = make_settings(
        database_url=_async_url(), storage_backend="postgres", run_worker=False
    )
    return create_app(settings, run_worker=False)


@pytest.mark.asyncio
async def test_rebuild_projection_restores_drifted_rows(pg_app) -> None:
    async with pg_app.router.lifespan_context(pg_app):
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            case = valid_case(
                steps=[
                    {"index": 1, "action": "点击开始", "expected": "已开始"},
                    {"index": 2, "action": "点击发现"},
                ]
            )
            created = await client.post(
                "/v1/reviews", json=review_payload(case=case), headers=auth_headers()
            )
            review_id = created.json()["review_id"]
            assert await pg_app.state.worker.run_once() == "done"

        storage = pg_app.state.storage
        expected = await storage.list_issues(review_id)
        assert expected

        # 模拟投影漂移：清空投影后一致性检查必须失败
        await storage.replace_issues(review_id, [])
        check_before = _run_script("check_consistency.py", "--review", review_id)
        assert check_before.returncode == 1, check_before.stdout + check_before.stderr
        assert "ISSUE-" in check_before.stdout

        rebuild = _run_script("rebuild_projection.py", "--review", review_id)
        assert rebuild.returncode == 0, rebuild.stdout + rebuild.stderr
        restored = await storage.list_issues(review_id)
        assert [record.issue_no for record in restored] == [
            record.issue_no for record in expected
        ]

        check_after = _run_script("check_consistency.py", "--review", review_id)
        assert check_after.returncode == 0, check_after.stdout + check_after.stderr
