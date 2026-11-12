import asyncio
from unittest.mock import AsyncMock

from app.storage.postgres import _PooledStorage


async def test_simultaneous_first_access_creates_one_pool(monkeypatch):
    pool = object()

    async def slow_create(*args, **kwargs):
        await asyncio.sleep(0.01)
        return pool

    create = AsyncMock(side_effect=slow_create)
    monkeypatch.setattr("app.storage.postgres.asyncpg.create_pool", create)
    storage = _PooledStorage("postgresql://unused/unused_test")
    results = await asyncio.gather(*(storage._get_pool() for _ in range(8)))
    assert all(item is pool for item in results)
    create.assert_awaited_once()
