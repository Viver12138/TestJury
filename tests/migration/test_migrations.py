"""ACC-M0-003：空库迁移成功、扩展存在、回滚一次后可重建。"""

from __future__ import annotations

import asyncio

import asyncpg

from tests.pg import dsn as _dsn
from tests.pg import run_alembic

CORE_TABLES = {
    "review_jobs",
    "review_decisions",
    "review_stages",
    "review_candidates",
    "issue_votes",
}


async def _tables() -> set[str]:
    conn = await asyncpg.connect(_dsn())
    try:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )
    finally:
        await conn.close()
    return {row["tablename"] for row in rows}


async def _extensions() -> set[str]:
    conn = await asyncpg.connect(_dsn())
    try:
        rows = await conn.fetch("SELECT extname FROM pg_extension")
    finally:
        await conn.close()
    return {row["extname"] for row in rows}


async def _alembic_version() -> str | None:
    conn = await asyncpg.connect(_dsn())
    try:
        return await conn.fetchval("SELECT version_num FROM alembic_version")
    finally:
        await conn.close()


def test_empty_database_migrates_and_rolls_back(clean_database: str) -> None:
    upgrade = run_alembic("upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    assert {"vector", "pgcrypto", "pg_trgm"} <= asyncio.run(_extensions())
    tables = asyncio.run(_tables())
    assert CORE_TABLES <= tables
    assert "review_attachments" in tables
    assert asyncio.run(_alembic_version()) == "0002_m1_review_attachments"

    # 回滚一个 revision：只撤销附件绑定表，不破坏 M0 核心表
    downgrade_one = run_alembic("downgrade", "-1")
    assert downgrade_one.returncode == 0, downgrade_one.stdout + downgrade_one.stderr
    after_one = asyncio.run(_tables())
    assert "review_attachments" not in after_one
    assert CORE_TABLES <= after_one
    assert asyncio.run(_alembic_version()) == "0001_m0_initial"

    # 再回滚到 base：核心表被撤销
    downgrade_all = run_alembic("downgrade", "-1")
    assert downgrade_all.returncode == 0, downgrade_all.stdout + downgrade_all.stderr
    remaining = asyncio.run(_tables())
    assert CORE_TABLES.isdisjoint(remaining), remaining
    assert "api_keys" not in remaining

    rebuild = run_alembic("upgrade", "head")
    assert rebuild.returncode == 0, rebuild.stdout + rebuild.stderr
    rebuilt = asyncio.run(_tables())
    assert CORE_TABLES <= rebuilt
    assert "review_attachments" in rebuilt
    assert asyncio.run(_alembic_version()) == "0002_m1_review_attachments"


def test_repeated_upgrade_is_noop(clean_database: str) -> None:
    first = run_alembic("upgrade", "head")
    assert first.returncode == 0, first.stdout + first.stderr
    second = run_alembic("upgrade", "head")
    assert second.returncode == 0, second.stdout + second.stderr

