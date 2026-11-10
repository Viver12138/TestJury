"""PostgreSQL 测试辅助：DSN、schema 重置与 Alembic 调用。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import asyncpg

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://testjury:testjury@127.0.0.1:55432/testjury"
)


def dsn() -> str:
    return TEST_DATABASE_URL


async def reset_schema() -> None:
    conn = await asyncpg.connect(dsn())
    try:
        await conn.execute("DROP SCHEMA public CASCADE")
        await conn.execute("CREATE SCHEMA public")
    finally:
        await conn.close()


async def probe() -> None:
    conn = await asyncpg.connect(dsn())
    await conn.close()


def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["DATABASE_URL"] = dsn()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(REPO_ROOT / "alembic.ini"), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )


def available() -> bool:
    try:
        asyncio.run(probe())
        return True
    except Exception:
        return False
