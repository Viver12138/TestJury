"""Alembic 环境：使用 async engine（asyncpg），URL 来自 DATABASE_URL / ALEMBIC_DATABASE_URL。"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not url:
    raise RuntimeError("缺少 DATABASE_URL / ALEMBIC_DATABASE_URL，无法执行迁移")
if url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql+asyncpg://", 1)
config.set_main_option("sqlalchemy.url", url)

target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
