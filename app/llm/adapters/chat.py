"""OpenAI 兼容 Chat Adapter（不依赖具体供应商）。

只负责协议：请求序列化、HTTP 错误分类、响应解析；Prompt 组装与输出业务校验在流水线层。
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.llm.adapters.common import delete_client, post_json
from app.llm.base import (
    AdapterError,
    ChatRequest,
    ChatResponse,
    TokenUsage,
)


class OpenAICompatibleChatAdapter:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        model_id: str,
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model_id
        self.timeout = timeout
        self._client = client
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._client is not None:
            await delete_client(self._client, self._owns_client)
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def complete(self, request: ChatRequest) -> ChatResponse:
        model = request.model or self.model_id
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": item.role, "content": item.content} for item in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.response_format is not None:
            payload["response_format"] = request.response_format

        started = time.perf_counter()
        response = await post_json(
            self._get_client(),
            f"{self.base_url}/chat/completions",
            payload,
            headers=self._headers(),
            timeout=request.timeout or self.timeout,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        try:
            body = response.json()
        except ValueError as exc:
            raise AdapterError("OUTPUT_INVALID", "响应不是合法 JSON", retryable=False) from exc
        if not isinstance(body, dict):
            raise AdapterError("OUTPUT_INVALID", "响应必须是 JSON 对象", retryable=False)

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise AdapterError("OUTPUT_INVALID", "响应缺少 choices", retryable=False)
        message = choices[0].get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise AdapterError("OUTPUT_INVALID", "响应缺少 message.content", retryable=False)
        if choices[0].get("finish_reason") == "length":
            # 截断不得静默当成完整输出（docs/10 §7.1）
            raise AdapterError("OUTPUT_TRUNCATED", "模型输出被截断", retryable=True)

        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        return ChatResponse(
            text=message["content"],
            model=str(body.get("model") or model),
            model_version=str(body.get("model")) if body.get("model") else None,
            usage=TokenUsage(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
            ),
            latency_ms=latency_ms,
            raw=body,
        )
