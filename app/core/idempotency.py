"""幂等与内容指纹（docs/03 §1.1 为唯一口径）。

```
input_hash      = sha256(规范化 case + test_scope + automation_context + 影响结论的 options)
idempotency_key = sha256(input_hash + 各版本号)
```

- `case_version` 不参与内容指纹：业务版本变化不触发重评；
- `force` / `webhook_url` 不参与：它们不影响结论；
- 规范化必须固定：空白折叠、键排序、附件只保留 sha256。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.core.versioning import Versions

_WHITESPACE = re.compile(r"\s+")
_EXCLUDED_CASE_FIELDS = {"case_version"}


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize(item)
            for key, item in sorted(value.items())
            if key not in _EXCLUDED_CASE_FIELDS
        }
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return _WHITESPACE.sub(" ", value.strip())
    return value


def canonical_payload(
    case: dict[str, Any],
    test_scope: dict[str, Any] | None,
    automation_context: dict[str, Any] | None,
    options: dict[str, Any],
) -> dict[str, Any]:
    comparable_options = {
        "strict_kb": bool(options.get("strict_kb", False)),
    }
    if options.get("budget_tokens") is not None:
        comparable_options["budget_tokens"] = options["budget_tokens"]

    normalized_case = dict(case)
    normalized_case["attachments"] = [
        {"sha256": attachment.get("sha256")}
        for attachment in (case.get("attachments") or [])
    ]
    return {
        "case": _normalize(normalized_case),
        "test_scope": _normalize(test_scope),
        "automation_context": _normalize(automation_context),
        "options": _normalize(comparable_options),
    }


def compute_input_hash(
    case: dict[str, Any],
    test_scope: dict[str, Any] | None,
    automation_context: dict[str, Any] | None,
    options: dict[str, Any],
) -> str:
    payload = canonical_payload(case, test_scope, automation_context, options)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compute_idempotency_key(input_hash: str, versions: Versions) -> str:
    components = versions.idempotency_components()
    encoded = json.dumps(
        {"input_hash": input_hash, **components}, ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
