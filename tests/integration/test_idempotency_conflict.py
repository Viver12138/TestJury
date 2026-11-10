"""ACC-CON-004：同键不同请求体被拒绝；内容变化必须改变服务端计算的 key。"""

from __future__ import annotations

import pytest

from app.core.auth import Principal
from app.core.enums import ActorType
from app.core.errors import ApiError, ErrorCode
from tests.helpers import review_payload, valid_case


def _principal() -> Principal:
    return Principal(
        actor_id="reviewer-1",
        actor_type=ActorType.HUMAN,
        roles=frozenset({"reviewer"}),
        caller_id=None,
    )


@pytest.mark.asyncio
async def test_same_explicit_key_with_different_body_is_rejected(app) -> None:
    service = app.state.review_service
    principal = _principal()
    payload_a = review_payload(case=valid_case("TC-A"))
    payload_b = review_payload(case=valid_case("TC-B", title="另一个用例"))

    first = await service.submit(payload_a, principal, idempotency_key="fixed-key")
    assert first.status_code == 202

    with pytest.raises(ApiError) as excinfo:
        await service.submit(payload_b, principal, idempotency_key="fixed-key")
    assert excinfo.value.code is ErrorCode.IDEMPOTENCY_KEY_CONFLICT

    jobs = await app.state.storage.list_jobs(limit=10)
    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_content_change_produces_different_key(app) -> None:
    service = app.state.review_service
    principal = _principal()

    first = await service.submit(review_payload(case=valid_case("TC-A")), principal)
    second = await service.submit(
        review_payload(case=valid_case("TC-B", title="另一个用例")), principal
    )
    assert first.status_code == second.status_code == 202

    job_a = await app.state.storage.get_job(first.body["review_id"])
    job_b = await app.state.storage.get_job(second.body["review_id"])
    assert job_a is not None and job_b is not None
    assert job_a.idempotency_key != job_b.idempotency_key
    assert job_a.input_hash != job_b.input_hash
