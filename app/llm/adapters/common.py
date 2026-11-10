"""HTTP 适配器共享逻辑：状态码分类、超时/连接错误映射。"""

from __future__ import annotations

from typing import Any

import httpx

from app.llm.base import AdapterError


def map_status_error(response: httpx.Response) -> AdapterError:
    status = response.status_code
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    if status == 429:
        return AdapterError("RATE_LIMITED", "供应商限流", retryable=True, status_code=status, raw=body)
    if status >= 500:
        return AdapterError(
            "PROVIDER_UNAVAILABLE", f"供应商 {status}", retryable=True, status_code=status, raw=body
        )
    return AdapterError(
        "PROVIDER_REJECTED", f"供应商拒绝请求 {status}", retryable=False, status_code=status, raw=body
    )


def map_transport_error(exc: Exception) -> AdapterError:
    if isinstance(exc, httpx.TimeoutException):
        return AdapterError("TIMEOUT", "模型调用超时", retryable=True)
    if isinstance(exc, httpx.TransportError):
        return AdapterError("CONNECTION_ERROR", "模型连接失败", retryable=True)
    return AdapterError("NETWORK_ERROR", f"模型调用失败: {exc}", retryable=True)


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout: float,
) -> httpx.Response:
    try:
        response = await client.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        raise map_transport_error(exc) from exc
    if response.status_code >= 400:
        raise map_status_error(response)
    return response


async def delete_client(client: httpx.AsyncClient, owned: bool) -> None:
    if owned:
        await client.aclose()
