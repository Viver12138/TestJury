"""统一错误码与错误响应（docs/19 为唯一规范）。

- 响应固定为 `{"error": {code, message, field?, retryable, request_id, details}}`。
- 4xx 不返回堆栈、SQL、供应商报文或密钥。
- 错误码可枚举，调用方只凭 code 决定重试/修正/放弃。
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.core.context import get_request_id

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    INVALID_JSON = "INVALID_JSON"
    INVALID_CASE = "INVALID_CASE"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    KB_MODULE_MISSING = "KB_MODULE_MISSING"
    DECISION_CONFLICT = "DECISION_CONFLICT"
    INVALID_DECISION_STATE = "INVALID_DECISION_STATE"
    REVIEW_IN_PROGRESS = "REVIEW_IN_PROGRESS"
    INPUT_INVALID = "INPUT_INVALID"
    UNSUPPORTED_TEST_TYPE = "UNSUPPORTED_TEST_TYPE"
    TEST_TYPE_REQUIRED = "TEST_TYPE_REQUIRED"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    TOO_MANY_CASES = "TOO_MANY_CASES"
    INVALID_DECISION = "INVALID_DECISION"
    QUEUE_FULL = "QUEUE_FULL"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    OUTPUT_SCHEMA_INVALID = "OUTPUT_SCHEMA_INVALID"
    ALL_MODELS_FAILED = "ALL_MODELS_FAILED"
    INTERNAL = "INTERNAL"
    # 框架级：仅用于路由/方法不匹配，保证 404/405 也走同一 envelope
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"


# code -> (HTTP status, retryable)
ERROR_SPECS: dict[ErrorCode, tuple[int, bool]] = {
    ErrorCode.INVALID_JSON: (400, False),
    ErrorCode.INVALID_CASE: (400, False),
    ErrorCode.UNAUTHORIZED: (401, False),
    ErrorCode.FORBIDDEN: (403, False),
    ErrorCode.NOT_FOUND: (404, False),
    ErrorCode.KB_MODULE_MISSING: (409, False),
    ErrorCode.DECISION_CONFLICT: (409, True),
    ErrorCode.INVALID_DECISION_STATE: (409, False),
    ErrorCode.REVIEW_IN_PROGRESS: (409, True),
    ErrorCode.INPUT_INVALID: (422, False),
    ErrorCode.UNSUPPORTED_TEST_TYPE: (422, False),
    ErrorCode.TEST_TYPE_REQUIRED: (422, False),
    ErrorCode.IDEMPOTENCY_KEY_CONFLICT: (422, False),
    ErrorCode.TOO_MANY_CASES: (422, False),
    ErrorCode.INVALID_DECISION: (422, False),
    ErrorCode.QUEUE_FULL: (429, True),
    ErrorCode.BUDGET_EXCEEDED: (429, False),
    ErrorCode.OUTPUT_SCHEMA_INVALID: (502, False),
    ErrorCode.ALL_MODELS_FAILED: (503, True),
    ErrorCode.INTERNAL: (500, True),
    ErrorCode.METHOD_NOT_ALLOWED: (405, False),
}


class ApiError(Exception):
    """业务错误：由 API 层抛出，统一转换为 docs/19 envelope。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.details = details or {}
        self.headers = headers or {}
        self.http_status, self.retryable = ERROR_SPECS[code]

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": str(self.code),
            "message": self.message,
            "retryable": self.retryable,
            "request_id": get_request_id(),
        }
        if self.field:
            payload["field"] = self.field
        payload["details"] = self.details
        return {"error": payload}


def error_payload(
    code: ErrorCode,
    message: str,
    *,
    field: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _, retryable = ERROR_SPECS[code]
    payload: dict[str, Any] = {
        "code": str(code),
        "message": message,
        "retryable": retryable,
        "request_id": get_request_id(),
    }
    if field:
        payload["field"] = field
    payload["details"] = details or {}
    return {"error": payload}


def _first_field(errors: list[dict[str, Any]]) -> str | None:
    for error in errors:
        loc = [str(part) for part in error.get("loc", ()) if part not in ("body", "query", "path")]
        if loc:
            return ".".join(loc)
    return None


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_payload(), headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        is_json_error = any(error.get("type") == "json_invalid" for error in errors)
        if is_json_error:
            return JSONResponse(
                status_code=400,
                content=error_payload(ErrorCode.INVALID_JSON, "请求体不是合法 JSON"),
            )
        field = _first_field(errors)
        message = f"{field} 不合法" if field else "请求体校验失败"
        if field and errors:
            raw = errors[0].get("msg")
            if raw:
                message = f"{field}: {raw}"
        return JSONResponse(
            status_code=422,
            content=error_payload(ErrorCode.INPUT_INVALID, message, field=field),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return JSONResponse(
                status_code=404,
                content=error_payload(ErrorCode.NOT_FOUND, "资源不存在"),
            )
        if exc.status_code == 405:
            return JSONResponse(
                status_code=405,
                content=error_payload(ErrorCode.METHOD_NOT_ALLOWED, "请求方法不允许"),
            )
        if 400 <= exc.status_code < 500:
            return JSONResponse(
                status_code=exc.status_code,
                content=error_payload(ErrorCode.INPUT_INVALID, str(exc.detail)),
            )
        return JSONResponse(
            status_code=500,
            content=error_payload(ErrorCode.INTERNAL, "服务内部错误"),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=500,
            content=error_payload(ErrorCode.INTERNAL, "服务内部错误"),
        )
