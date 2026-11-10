"""OpenAI 兼容 Embedding Adapter：维度必须与 profile 一致，禁止混用向量。"""

from __future__ import annotations

from typing import Any

import httpx

from app.llm.adapters.common import delete_client, post_json
from app.llm.base import AdapterError, EmbeddingResponse, TokenUsage


class OpenAICompatibleEmbeddingAdapter:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        model_id: str,
        dimension: int,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model_id
        self.dimension = dimension
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

    async def embed(
        self, texts: list[str], *, model: str | None = None
    ) -> EmbeddingResponse:
        if not texts:
            raise AdapterError("INPUT_INVALID", "embedding 输入不能为空", retryable=False)
        payload: dict[str, Any] = {"model": model or self.model_id, "input": texts}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = await post_json(
            self._get_client(),
            f"{self.base_url}/embeddings",
            payload,
            headers=headers,
            timeout=self.timeout,
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise AdapterError("OUTPUT_INVALID", "embedding 响应不是 JSON", retryable=False) from exc
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != len(texts):
            raise AdapterError(
                "OUTPUT_INVALID", "embedding 返回条数与输入不一致", retryable=False
            )

        ordered = sorted(data, key=lambda item: item.get("index", 0) if isinstance(item, dict) else 0)
        vectors: list[list[float]] = []
        for item in ordered:
            vector = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(vector, list) or not vector:
                raise AdapterError("OUTPUT_INVALID", "embedding 向量缺失", retryable=False)
            if len(vector) != self.dimension:
                raise AdapterError(
                    "DIMENSION_MISMATCH",
                    f"向量维度 {len(vector)} 与 profile {self.dimension} 不一致",
                    retryable=False,
                )
            vectors.append([float(value) for value in vector])

        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        return EmbeddingResponse(
            vectors=vectors,
            model=str(body.get("model") or model or self.model_id),
            dimension=self.dimension,
            usage=TokenUsage(input_tokens=int(usage.get("prompt_tokens") or 0)),
            raw=body,
        )
