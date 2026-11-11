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
    assert asyncio.run(_alembic_version()) == "0004_m1_masking_audit"

    # 回滚 0004：只撤销脱敏审计列
    downgrade_0004 = run_alembic("downgrade", "0003_m1_audit_evidence")
    assert downgrade_0004.returncode == 0, downgrade_0004.stdout + downgrade_0004.stderr
    assert asyncio.run(_alembic_version()) == "0003_m1_audit_evidence"

    # 回滚 0003：只撤销审计/证据列，不破坏附件表与 M0 核心表
    downgrade_0003 = run_alembic("downgrade", "0002_m1_review_attachments")
    assert downgrade_0003.returncode == 0, downgrade_0003.stdout + downgrade_0003.stderr
    after_0003 = asyncio.run(_tables())
    assert "review_attachments" in after_0003
    assert CORE_TABLES <= after_0003
    assert asyncio.run(_alembic_version()) == "0002_m1_review_attachments"

    # 再回滚一个 revision：只撤销附件绑定表
    downgrade_0002 = run_alembic("downgrade", "0001_m0_initial")
    assert downgrade_0002.returncode == 0, downgrade_0002.stdout + downgrade_0002.stderr
    after_0002 = asyncio.run(_tables())
    assert "review_attachments" not in after_0002
    assert CORE_TABLES <= after_0002
    assert asyncio.run(_alembic_version()) == "0001_m0_initial"

    # 再回滚到 base：核心表被撤销
    downgrade_all = run_alembic("downgrade", "base")
    assert downgrade_all.returncode == 0, downgrade_all.stdout + downgrade_all.stderr
    remaining = asyncio.run(_tables())
    assert CORE_TABLES.isdisjoint(remaining), remaining
    assert "api_keys" not in remaining

    rebuild = run_alembic("upgrade", "head")
    assert rebuild.returncode == 0, rebuild.stdout + rebuild.stderr
    rebuilt = asyncio.run(_tables())
    assert CORE_TABLES <= rebuilt
    assert "review_attachments" in rebuilt
    assert asyncio.run(_alembic_version()) == "0004_m1_masking_audit"


def test_repeated_upgrade_is_noop(clean_database: str) -> None:
    first = run_alembic("upgrade", "head")
    assert first.returncode == 0, first.stdout + first.stderr
    second = run_alembic("upgrade", "head")
    assert second.returncode == 0, second.stdout + second.stderr



