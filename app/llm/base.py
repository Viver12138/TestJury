"""模型适配层契约（docs/06 §3.6、docs/10 §7.4）。

M1 的 Adapter 只定义协议与请求/响应结构，不绑定供应商：
- Chat / Embedding / Rerank 三类适配器各自独立，不套用聊天接口；
- `AdapterError` 区分可重试（超时/5xx/429/连接）与不可重试（4xx/输出非法）；
- `ReviewModel` 是评审流水线依赖的领域接口，Mock 与真实适配器都必须满足。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ChatRequest:
    messages: list[ChatMessage]
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    response_format: dict[str, Any] | None = None
    timeout: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ChatResponse:
    text: str
    model: str
    model_version: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: int | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class EmbeddingResponse:
    vectors: list[list[float]]
    model: str
    dimension: int
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class RerankHit:
    index: int
    score: float
    document: str | None = None


@dataclass(frozen=True)
class RerankResponse:
    hits: list[RerankHit]
    model: str


class AdapterError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        status_code: int | None = None,
        raw: Any = None,
    ) -> None:
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.raw = raw
        super().__init__(f"{code}: {message}")


class ChatAdapter(Protocol):
    async def complete(self, request: ChatRequest) -> ChatResponse: ...


class EmbeddingAdapter(Protocol):
    async def embed(
        self, texts: list[str], *, model: str | None = None
    ) -> EmbeddingResponse: ...


class RerankAdapter(Protocol):
    async def rerank(
        self, query: str, documents: list[str], *, top_n: int | None = None
    ) -> RerankResponse: ...


@dataclass
class ReviewOpinion:
    """一次盲评的领域输出；模型返回的决策/状态字段不得进入该结构。"""

    role: str
    summary: str
    issues: list[dict[str, Any]] = field(default_factory=list)


class ReviewModel(Protocol):
    def review(self, role: str, case: dict[str, Any]) -> ReviewOpinion: ...


def parse_json_object(text: str) -> dict[str, Any]:
    """解析模型 JSON 输出；允许 ```json 围栏，失败抛不可重试错误。"""

    import json
    import re

    cleaned = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AdapterError(
            "OUTPUT_INVALID", f"模型输出不是合法 JSON: {exc.msg}", retryable=False
        ) from exc
    if not isinstance(payload, dict):
        raise AdapterError("OUTPUT_INVALID", "模型 JSON 输出必须是对象", retryable=False)
    return payload
