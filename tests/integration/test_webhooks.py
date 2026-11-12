import asyncio
import hashlib
import hmac
import json

import httpx
import pytest

from app.core.auth import Principal
from app.core.enums import ActorType
from app.core.webhooks import WebhookWorker, deliver, validate_webhook_url
from app.main import create_app
from tests.helpers import make_settings, review_payload


def settings(**extra):
    return make_settings(webhook_enabled=True, webhook_secret="test-only-signing-secret-1234567890",
                         webhook_allowed_hosts="callback.example", **extra)


async def exercise_outbox(config):
    app = create_app(config, run_worker=False)
    actor = Principal("callback-test", ActorType.SERVICE, frozenset({"reviewer"}), None)
    payload = review_payload(options={"webhook_url": "https://callback.example/complete"})
    submitted = await app.state.review_service.submit(payload, actor)
    try:
        await app.state.worker.run_once()
        await asyncio.gather(app.state.storage.enqueue_webhooks(), app.state.storage.enqueue_webhooks())
        claims = await asyncio.gather(*(app.state.storage.claim_webhook(60, 5) for _ in range(2)))
        assert sum(row is not None for row in claims) == 1
        event = next(row for row in claims if row is not None)
        assert set(event["payload"]) == {"review_id", "ai_verdict", "human_status", "summary"}
        assert event["payload"]["review_id"] == submitted.body["review_id"]
        await app.state.storage.finish_webhook(event["event_id"], 1, False, 0, 5, "TimeoutError")
        sent = []

        async def sender(row, config):
            sent.append(row)

        # A newly constructed delivery worker recovers the durable pending event.
        worker = WebhookWorker(app.state.storage, config, sender=sender)
        assert await worker.run_once() == "delivered"
        assert sent[0]["event_id"] == event["event_id"]
        assert sent[0]["attempts"] == 2
        await app.state.storage.finish_webhook(event["event_id"], 1, False, 0, 5, "stale_sender")
        assert await worker.run_once() is None
    finally:
        close = getattr(app.state.storage, "close", None)
        if close:
            await close()


async def test_memory_webhook_retry_identity_and_restart():
    await exercise_outbox(settings())


@pytest.mark.postgres
async def test_postgres_webhook_retry_identity_and_restart(migrated_database):
    await exercise_outbox(settings(storage_backend="postgres", database_url=migrated_database))


async def test_signature_pinned_ip_and_redirect_refusal():
    config = settings()
    seen = []

    async def handler(request):
        seen.append(request)
        expected = hmac.new(config.webhook_secret.encode(), request.headers["X-Timestamp"].encode()
                            + b"." + request.content, hashlib.sha256).hexdigest()
        assert request.headers["X-Signature"] == "sha256=" + expected
        assert request.headers["Host"] == "callback.example"
        assert request.url.host == "8.8.8.8"
        assert request.extensions["sni_hostname"] == "callback.example"
        assert json.loads(request.content) == {"review_id": "r1"}
        return httpx.Response(307, headers={"Location": "https://127.0.0.1/private"})

    async def resolve(host):
        return ["8.8.8.8"]

    event = {"event_id": "r1:review.done:1", "url": "https://callback.example/done", "payload": {"review_id": "r1"}}
    with pytest.raises(ValueError, match="callback_http_307"):
        await deliver(event, config, transport=httpx.MockTransport(handler), resolver=resolve)
    assert len(seen) == 1

    async def private(host):
        return ["8.8.8.8", "127.0.0.1"]

    with pytest.raises(ValueError, match="受限网络"):
        await deliver(event, config, transport=httpx.MockTransport(handler), resolver=private)
    assert len(seen) == 1


@pytest.mark.parametrize("url", ["http://callback.example/done", "https://evil.example/done",
                                      "https://callback.example:444/done", "https://user:pass@callback.example/done"])
def test_unsafe_callback_address_is_rejected(url):
    with pytest.raises(ValueError):
        validate_webhook_url(url, settings())
