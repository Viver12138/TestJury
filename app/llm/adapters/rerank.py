"""Rerank Adapter：独立协议，不套用聊天接口（docs/06 §3.6）。"""

from __future__ import annotations

from typing import Any

import httpx

from app.llm.adapters.common import delete_client, post_json
from app.llm.base import AdapterError, RerankHit, RerankResponse


class HttpRerankAdapter:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        model_id: str,
        timeout: float = 20.0,
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

    async def rerank(
        self, query: str, documents: list[str], *, top_n: int | None = None
    ) -> RerankResponse:
        if not documents:
            raise AdapterError("INPUT_INVALID", "rerank 文档不能为空", retryable=False)
        payload: dict[str, Any] = {
            "model": self.model_id,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = await post_json(
            self._get_client(),
            f"{self.base_url}/rerank",
            payload,
            headers=headers,
            timeout=self.timeout,
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise AdapterError("OUTPUT_INVALID", "rerank 响应不是 JSON", retryable=False) from exc

        results = body.get("results") if isinstance(body, dict) else None
        if results is None and isinstance(body, dict) and isinstance(body.get("output"), dict):
            results = body["output"].get("results")
        if not isinstance(results, list) or not results:
            raise AdapterError("OUTPUT_INVALID", "rerank 响应缺少 results", retryable=False)

        hits: list[RerankHit] = []
        for item in results:
            if not isinstance(item, dict):
                raise AdapterError("OUTPUT_INVALID", "rerank 结果项必须是对象", retryable=False)
            index = item.get("index")
            score = item.get("relevance_score", item.get("score"))
            if not isinstance(index, int) or not (0 <= index < len(documents)):
                raise AdapterError("OUTPUT_INVALID", f"rerank index 越界: {index!r}", retryable=False)
            if not isinstance(score, (int, float)):
                raise AdapterError("OUTPUT_INVALID", "rerank 分数非法", retryable=False)
            hits.append(
                RerankHit(index=index, score=float(score), document=documents[index])
            )
        hits.sort(key=lambda hit: hit.score, reverse=True)
        if top_n is not None:
            hits = hits[:top_n]
        return RerankResponse(hits=hits, model=str(body.get("model") or self.model_id))
