"""API 同步硬校验（docs/03 §1、docs/06 §3.12）。

硬错误在创建任务前返回 400/422，不建任务、不返回 202；
`input_quality` 的软问题由 Worker 阶段的 `soft_check` 产生，不在这里返回 422。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.core.enums import TestType, TestTypeSource
from app.core.errors import ApiError, ErrorCode
from app.core.webhooks import validate_webhook_url

PRIORITIES = {"P0", "P1", "P2", "P3"}
CASE_SOURCES = {"manual", "auto"}


@dataclass
class NormalizedRequest:
    case: dict[str, Any]
    test_scope: dict[str, Any] | None
    automation_context: dict[str, Any] | None
    options: dict[str, Any]
    test_type_source: str
    warnings: list[str] = field(default_factory=list)


def _fail(code: ErrorCode, message: str, field: str | None = None) -> None:
    raise ApiError(code, message, field=field)


def _as_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _require_text(value: Any, field_path: str, *, max_length: int | None = None) -> str:
    text = _as_str(value)
    if not text:
        _fail(ErrorCode.INPUT_INVALID, f"{field_path} 不能为空", field_path)
    if max_length is not None and len(text) > max_length:
        _fail(ErrorCode.INPUT_INVALID, f"{field_path} 超过长度上限", field_path)
    return text


def _validate_test_type(
    case: dict[str, Any], settings: Settings, caller_id: str | None
) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    raw = case.get("test_type", None)
    if raw is None or _as_str(raw) == "":
        if settings.test_type_default_policy == "compat" and caller_id in settings.compat_callers:
            warnings.append(
                "test_type 缺失，按兼容模式视为 functional（test_type_source=compat_default）"
            )
            return TestType.FUNCTIONAL.value, TestTypeSource.COMPAT_DEFAULT.value, warnings
        _fail(
            ErrorCode.TEST_TYPE_REQUIRED,
            "case.test_type 必填；v1 仅支持 functional（缺失不推断）",
            "case.test_type",
        )

    value = _as_str(raw)
    if value not in {item.value for item in TestType}:
        _fail(
            ErrorCode.INPUT_INVALID,
            f"case.test_type 非法: {value!r}",
            "case.test_type",
        )
    if value != TestType.FUNCTIONAL.value:
        _fail(
            ErrorCode.UNSUPPORTED_TEST_TYPE,
            f"v1 仅支持 functional，收到 {value!r}；不创建任务、不出质量结论",
            "case.test_type",
        )
    return value, TestTypeSource.REQUEST.value, warnings


def _validate_steps(steps: Any) -> list[dict[str, Any]]:
    if steps is None:
        return []
    if not isinstance(steps, list):
        _fail(ErrorCode.INVALID_CASE, "case.steps 必须是数组", "case.steps")

    normalized: list[dict[str, Any]] = []
    for position, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            _fail(ErrorCode.INVALID_CASE, f"case.steps[{position - 1}] 必须是对象", "case.steps")
        index = step.get("index", position)
        if not isinstance(index, int) or isinstance(index, bool) or index != position:
            _fail(
                ErrorCode.INVALID_CASE,
                f"case.steps[{position - 1}].index 必须从 1 连续递增（期望 {position}）",
                f"case.steps[{position - 1}].index",
            )
        action = _require_text(step.get("action"), f"case.steps[{position - 1}].action")
        expected = step.get("expected")
        if expected is not None and _as_str(expected) == "":
            expected = None
        normalized.append(
            {
                "index": position,
                "action": action,
                "expected": expected.strip() if isinstance(expected, str) else None,
            }
        )
    return normalized


def _validate_attachments(attachments: Any) -> list[dict[str, Any]]:
    if attachments is None:
        return []
    if not isinstance(attachments, list):
        _fail(ErrorCode.INVALID_CASE, "case.attachments 必须是数组", "case.attachments")
    result: list[dict[str, Any]] = []
    for position, attachment in enumerate(attachments):
        if not isinstance(attachment, dict):
            _fail(
                ErrorCode.INVALID_CASE,
                f"case.attachments[{position}] 必须是对象",
                "case.attachments",
            )
        attachment_id = _require_text(
            attachment.get("attachment_id"), f"case.attachments[{position}].attachment_id"
        )
        sha256 = _require_text(attachment.get("sha256"), f"case.attachments[{position}].sha256")
        result.append(
            {
                "attachment_id": attachment_id,
                "file_name": _as_str(attachment.get("file_name")) or attachment_id,
                "sha256": sha256,
            }
        )
    return result


def validate_request(
    payload: Any, settings: Settings, *, caller_id: str | None = None
) -> NormalizedRequest:
    if not isinstance(payload, dict):
        _fail(ErrorCode.INVALID_JSON, "请求体必须是 JSON 对象")

    case = payload.get("case")
    if not isinstance(case, dict):
        _fail(ErrorCode.INVALID_CASE, "case 必须是对象", "case")

    case_id = _require_text(case.get("case_id"), "case.case_id")
    module = _require_text(case.get("module"), "case.module")
    title = _require_text(case.get("title"), "case.title")

    test_type, test_type_source, warnings = _validate_test_type(case, settings, caller_id)
    steps = _validate_steps(case.get("steps"))
    raw_text = _as_str(case.get("raw_text"))

    if not steps and not raw_text:
        _fail(
            ErrorCode.INPUT_INVALID,
            "case.steps 与 case.raw_text 不能同时为空",
            "case.steps",
        )
    if len(raw_text) > settings.input_max_chars:
        _fail(ErrorCode.INPUT_INVALID, "case.raw_text 超过输入上限", "case.raw_text")
    if len(steps) > 200:
        _fail(ErrorCode.INPUT_INVALID, "case.steps 数量超过上限", "case.steps")

    case_version = case.get("case_version", 1)
    if not isinstance(case_version, int) or isinstance(case_version, bool) or case_version < 1:
        _fail(ErrorCode.INPUT_INVALID, "case.case_version 必须是 >=1 的整数", "case.case_version")

    source = _as_str(case.get("source")) or "manual"
    if source not in CASE_SOURCES:
        _fail(ErrorCode.INPUT_INVALID, f"case.source 非法: {source!r}", "case.source")

    priority = case.get("priority")
    if priority is not None and priority not in PRIORITIES:
        _fail(ErrorCode.INPUT_INVALID, f"case.priority 非法: {priority!r}", "case.priority")

    test_scope = payload.get("test_scope")
    if test_scope is not None and not isinstance(test_scope, dict):
        _fail(ErrorCode.INPUT_INVALID, "test_scope 必须是对象", "test_scope")

    automation_context = payload.get("automation_context")
    if automation_context is not None and not isinstance(automation_context, dict):
        _fail(
            ErrorCode.INPUT_INVALID,
            "automation_context 必须是对象",
            "automation_context",
        )

    raw_options = payload.get("options") or {}
    if not isinstance(raw_options, dict):
        _fail(ErrorCode.INPUT_INVALID, "options 必须是对象", "options")
    requested_budget = raw_options.get("budget_tokens")
    if requested_budget is not None and (type(requested_budget) is not int or requested_budget < 1):
        _fail(ErrorCode.INPUT_INVALID, "budget_tokens 必须是正整数", "options.budget_tokens")
    if raw_options.get("webhook_url") is not None:
        try:
            validate_webhook_url(raw_options["webhook_url"], settings)
        except ValueError as exc:
            _fail(ErrorCode.INPUT_INVALID, str(exc), "options.webhook_url")
    options = {
        "force": bool(raw_options.get("force", False)),
        "strict_kb": bool(raw_options.get("strict_kb", False)),
        "webhook_url": raw_options.get("webhook_url"),
        "budget_tokens": raw_options.get("budget_tokens"),
    }

    normalized_case = {
        "case_id": case_id,
        "case_version": case_version,
        "module": module,
        "test_type": test_type,
        "title": title,
        "priority": priority,
        "source": source,
        "preconditions": list(case.get("preconditions") or []),
        "steps": steps,
        "test_data": case.get("test_data"),
        "attachments": _validate_attachments(case.get("attachments")),
        "raw_text": raw_text or None,
        "kb_hint": case.get("kb_hint"),
    }
    if case.get("project_id") is not None:
        normalized_case["project_id"] = _require_text(case["project_id"], "case.project_id", max_length=100)
        baseline = _require_text(case.get("review_baseline"), "case.review_baseline")
        if baseline not in {"current_implementation", "target_specification"}:
            _fail(ErrorCode.INPUT_INVALID, "未知评审基线", "case.review_baseline")
        normalized_case["review_baseline"] = baseline
        normalized_case["product_version"] = _require_text(case.get("product_version"), "case.product_version")
        normalized_case["platform"] = _as_str(case.get("platform")) or "all"
    if test_scope is not None:
        normalized_scope = {
            "feature_point": test_scope.get("feature_point"),
            "required_scenarios": list(test_scope.get("required_scenarios") or []),
            "related_case_ids": list(test_scope.get("related_case_ids") or []),
            "scope_version": test_scope.get("scope_version"),
        }
    else:
        normalized_scope = None

    normalized_context = dict(automation_context) if automation_context is not None else None

    return NormalizedRequest(
        case=normalized_case,
        test_scope=normalized_scope,
        automation_context=normalized_context,
        options=options,
        test_type_source=test_type_source,
        warnings=warnings,
    )


def soft_check(case: dict[str, Any]) -> dict[str, list[str]]:
    """Worker 软校验：只记 `input_quality`，不阻断评审。"""

    soft: list[str] = []
    steps = case.get("steps") or []
    seen_actions: dict[str, int] = {}
    for step in steps:
        index = step.get("index")
        if not step.get("expected"):
            soft.append(f"steps[{index}].expected 缺失")
        action = (step.get("action") or "").strip()
        if len(action) <= 3:
            soft.append(f"steps[{index}].action 描述过短")
        if action in seen_actions:
            soft.append(f"steps[{index}] 与 steps[{seen_actions[action]}] 操作重复")
        else:
            seen_actions[action] = index
    if not case.get("test_data"):
        soft.append("test_data 未提供具体值")
    if not case.get("preconditions"):
        soft.append("preconditions 缺失")
    return {"hard_errors": [], "soft_issues": soft}
