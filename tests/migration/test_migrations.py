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
    assert asyncio.run(_alembic_version()) == "0001_m0_initial"

    downgrade = run_alembic("downgrade", "-1")
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
    remaining = asyncio.run(_tables())
    assert CORE_TABLES.isdisjoint(remaining), remaining
    assert "api_keys" not in remaining

    rebuild = run_alembic("upgrade", "head")
    assert rebuild.returncode == 0, rebuild.stdout + rebuild.stderr
    assert CORE_TABLES <= asyncio.run(_tables())


def test_repeated_upgrade_is_noop(clean_database: str) -> None:
    first = run_alembic("upgrade", "head")
    assert first.returncode == 0, first.stdout + first.stderr
    second = run_alembic("upgrade", "head")
    assert second.returncode == 0, second.stdout + second.stderr

