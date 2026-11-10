"""ACC-CON-003：同键并发提交不产生双 active、不返回 409。"""

from __future__ import annotations

import asyncio

import pytest

from tests.helpers import auth_headers, review_payload


@pytest.mark.asyncio
async def test_concurrent_submissions_are_serialized(async_client, app) -> None:
    payload = review_payload()

    async def submit() -> int:
        response = await async_client.post("/v1/reviews", json=payload, headers=auth_headers())
        assert response.status_code in (200, 202), response.text
        return response.status_code

    codes = await asyncio.gather(*[submit() for _ in range(10)])
    assert codes.count(202) == 1, codes
    assert codes.count(200) == 9, codes
    assert 409 not in codes

    jobs = await app.state.storage.list_jobs(limit=100)
    assert len(jobs) == 1
    assert jobs[0].superseded_by is None
