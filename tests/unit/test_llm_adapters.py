"""HTTP 适配器协议契约：用 MockTransport 验证请求/响应与错误分类，不访问供应商。"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.llm.adapters.chat import OpenAICompatibleChatAdapter
from app.llm.adapters.embedding import OpenAICompatibleEmbeddingAdapter
from app.llm.adapters.rerank import HttpRerankAdapter
from app.llm.base import AdapterError, ChatMessage, ChatRequest, parse_json_object
from app.llm.retry import call_with_retry


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://provider.test/v1"
    )


def _chat_adapter(client: httpx.AsyncClient) -> OpenAICompatibleChatAdapter:
    return OpenAICompatibleChatAdapter(
        "http://provider.test/v1", "test-key", model_id="vendor-chief", timeout=30, client=client
    )


@pytest.mark.asyncio
async def test_chat_success_builds_request_and_parses_response() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "vendor-chief-2026-10",
                "choices": [
                    {
                        "message": {"content": '{"issues": []}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    client = _client(handler)
    try:
        response = await _chat_adapter(client).complete(
            ChatRequest(
                messages=[ChatMessage(role="system", content="你是评审"), ChatMessage(role="user", content="用例")],
                max_tokens=256,
                response_format={"type": "json_object"},
            )
        )
    finally:
        await client.aclose()

    assert captured["path"] == "/v1/chat/completions"
    assert captured["auth"] == "Bearer test-key"
    assert captured["body"]["model"] == "vendor-chief"
    assert captured["body"]["messages"][0]["role"] == "system"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert response.text == '{"issues": []}'
    assert response.usage.input_tokens == 100
    assert response.usage.output_tokens == 20
    assert response.model == "vendor-chief-2026-10"


@pytest.mark.asyncio
async def test_chat_error_classification() -> None:
    async def run(status: int, body: dict | None = None) -> AdapterError:
        client = _client(lambda request: httpx.Response(status, json=body or {}))
        try:
            with pytest.raises(AdapterError) as excinfo:
                await _chat_adapter(client).complete(
                    ChatRequest(messages=[ChatMessage(role="user", content="x")])
                )
            return excinfo.value
        finally:
            await client.aclose()

    rate_limited = await run(429)
    assert rate_limited.code == "RATE_LIMITED" and rate_limited.retryable
    unavailable = await run(503)
    assert unavailable.code == "PROVIDER_UNAVAILABLE" and unavailable.retryable
    rejected = await run(400)
    assert rejected.code == "PROVIDER_REJECTED" and not rejected.retryable


@pytest.mark.asyncio
async def test_chat_timeout_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    client = _client(handler)
    try:
        with pytest.raises(AdapterError) as excinfo:
            await _chat_adapter(client).complete(
                ChatRequest(messages=[ChatMessage(role="user", content="x")])
            )
    finally:
        await client.aclose()
    assert excinfo.value.code == "TIMEOUT"
    assert excinfo.value.retryable


@pytest.mark.asyncio
async def test_chat_truncated_and_invalid_output_are_rejected() -> None:
    def truncated(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{}"}, "finish_reason": "length"}],
            },
        )

    client = _client(truncated)
    try:
        with pytest.raises(AdapterError) as excinfo:
            await _chat_adapter(client).complete(
                ChatRequest(messages=[ChatMessage(role="user", content="x")])
            )
    finally:
        await client.aclose()
    assert excinfo.value.code == "OUTPUT_TRUNCATED"

    def malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = _client(malformed)
    try:
        with pytest.raises(AdapterError) as excinfo:
            await _chat_adapter(client).complete(
                ChatRequest(messages=[ChatMessage(role="user", content="x")])
            )
    finally:
        await client.aclose()
    assert excinfo.value.code == "OUTPUT_INVALID"
    assert not excinfo.value.retryable


@pytest.mark.asyncio
async def test_embedding_dimension_and_count_validation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "vendor-embedding",
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 1.0, 0.0]},
                ],
            },
        )

    client = _client(handler)
    try:
        adapter = OpenAICompatibleEmbeddingAdapter(
            "http://provider.test/v1",
            "test-key",
            model_id="vendor-embedding",
            dimension=4,
            client=client,
        )
        response = await adapter.embed(["a", "b"])
        assert [vector[0] for vector in response.vectors] == [1.0, 0.0]

        with pytest.raises(AdapterError) as excinfo:
            await adapter.embed(["only-one"])
        assert excinfo.value.code == "OUTPUT_INVALID"
    finally:
        await client.aclose()

    wrong_dimension = _client(
        lambda request: httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [0.0, 1.0]}]}
        )
    )
    try:
        adapter = OpenAICompatibleEmbeddingAdapter(
            "http://provider.test/v1",
            "test-key",
            model_id="vendor-embedding",
            dimension=4,
            client=wrong_dimension,
        )
        with pytest.raises(AdapterError) as excinfo:
            await adapter.embed(["a"])
        assert excinfo.value.code == "DIMENSION_MISMATCH"
    finally:
        await wrong_dimension.aclose()


@pytest.mark.asyncio
async def test_rerank_sorts_scores_and_keeps_documents() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["query"] == "藏宝点"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 2, "relevance_score": 0.92},
                    {"index": 0, "relevance_score": 0.51},
                    {"index": 1, "relevance_score": 0.73},
                ]
            },
        )

    client = _client(handler)
    try:
        adapter = HttpRerankAdapter(
            "http://provider.test/v1", "test-key", model_id="vendor-rerank", client=client
        )
        response = await adapter.rerank("藏宝点", ["a", "b", "c"], top_n=2)
    finally:
        await client.aclose()

    assert [hit.index for hit in response.hits] == [2, 1]
    assert response.hits[0].document == "c"
    assert response.hits[0].score == 0.92


@pytest.mark.asyncio
async def test_retry_only_retries_retryable_errors() -> None:
    calls = {"retryable": 0, "fatal": 0}

    async def flaky_then_ok() -> str:
        calls["retryable"] += 1
        if calls["retryable"] < 3:
            raise AdapterError("PROVIDER_UNAVAILABLE", "5xx", retryable=True)
        return "ok"

    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    assert await call_with_retry(
        flaky_then_ok, base_delay=0.1, jitter=0, sleep=fake_sleep
    ) == "ok"
    assert calls["retryable"] == 3
    assert sleeps == [0.1, 0.2]

    async def fatal() -> str:
        calls["fatal"] += 1
        raise AdapterError("PROVIDER_REJECTED", "4xx", retryable=False)

    with pytest.raises(AdapterError):
        await call_with_retry(fatal, sleep=fake_sleep)
    assert calls["fatal"] == 1


def test_parse_json_object_handles_fences_and_rejects_arrays() -> None:
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(AdapterError) as excinfo:
        parse_json_object("[1, 2]")
    assert excinfo.value.code == "OUTPUT_INVALID"
