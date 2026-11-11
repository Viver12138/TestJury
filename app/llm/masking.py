"""模型请求脱敏策略（docs/10 数据安全准入）。

注意：`STORE_RAW_MODEL_IO=false` 只是不落盘，不等于脱敏。本模块在 Prompt 构造前
对 case / vote material 做真实替换，保证发送给供应商的内容不含常见 PII/密钥。
"""

from __future__ import annotations

import copy
import re
import threading
from dataclasses import dataclass, field
from typing import Any

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_CARD = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
BANK_CARD = re.compile(r"(?<!\d)\d{16,19}(?!\d)")
IPV4 = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")

SECRET_KEYS = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "session",
    "session_id",
    "api_key",
    "apikey",
    "private_key",
}

PII_KEYS = {
    "email",
    "phone",
    "mobile",
    "tel",
    "id_card",
    "id_number",
    "bank_card",
    "account",
    "address",
    "name",
    "display_name",
    "username",
    "real_name",
}


def normalize_key(key: str | None) -> str:
    """兼容 camelCase / snake_case / kebab-case。"""

    return re.sub(r"[^a-z0-9]", "", (key or "").lower())


SECRET_KEYS_NORMALIZED = {normalize_key(item) for item in SECRET_KEYS}
PII_KEYS_NORMALIZED = {normalize_key(item) for item in PII_KEYS}
PII_KEY_PREFIXES = (
    "phone",
    "mobile",
    "tel",
    "email",
    "idcard",
    "idnumber",
    "bankcard",
    "account",
    "address",
    "username",
    "displayname",
    "realname",
)
SECRET_KEY_PREFIXES = (
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "privatekey",
    "authorization",
    "cookie",
    "session",
)


def is_secret_key(key: str | None) -> bool:
    normalized = normalize_key(key)
    return normalized in SECRET_KEYS_NORMALIZED or any(
        normalized.startswith(prefix) for prefix in SECRET_KEY_PREFIXES
    )


def is_pii_key(key: str | None) -> bool:
    normalized = normalize_key(key)
    return normalized in PII_KEYS_NORMALIZED or any(
        normalized.startswith(prefix) for prefix in PII_KEY_PREFIXES
    )


@dataclass
class MaskingResult:
    data: Any
    report: dict[str, Any]


@dataclass
class MaskingPolicy:
    policy_id: str = "mask-pii-v1"
    version: str = "1.0"
    counts: dict[str, int] = field(default_factory=dict)
    _mapping: dict[str, str] = field(default_factory=dict, init=False)
    _counters: dict[str, int] = field(default_factory=dict, init=False)
    _known: dict[str, str] = field(default_factory=dict, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def _placeholder(self, kind: str, value: str) -> str:
        if value in self._mapping:
            return self._mapping[value]
        self._counters[kind] = self._counters.get(kind, 0) + 1
        placeholder = f"<{kind}_{self._counters[kind]}>"
        self._mapping[value] = placeholder
        self.counts[kind] = self.counts.get(kind, 0) + 1
        return placeholder

    def _mask_text(self, text: str) -> str:
        for value, kind in sorted(self._known.items(), key=lambda item: -len(item[0])):
            if value and value in text:
                text = text.replace(value, self._placeholder(kind, value))
        text = EMAIL.sub(lambda m: self._placeholder("EMAIL", m.group(0)), text)
        text = PHONE.sub(lambda m: self._placeholder("PHONE", m.group(0)), text)
        text = ID_CARD.sub(lambda m: self._placeholder("ID_CARD", m.group(0)), text)
        text = BANK_CARD.sub(lambda m: self._placeholder("BANK_CARD", m.group(0)), text)
        text = IPV4.sub(lambda m: self._placeholder("IP", m.group(0)), text)
        return text

    def _collect(self, key: str | None, value: Any) -> None:
        if isinstance(value, dict):
            for item_key, item in value.items():
                self._collect(str(item_key), item)
        elif isinstance(value, list):
            for item in value:
                self._collect(key, item)
        elif isinstance(value, str):
            if is_secret_key(key):
                self._known[value] = "SECRET"
            elif is_pii_key(key):
                if EMAIL.fullmatch(value):
                    self._known[value] = "EMAIL"
                elif PHONE.fullmatch(value):
                    self._known[value] = "PHONE"
                elif ID_CARD.fullmatch(value):
                    self._known[value] = "ID_CARD"
                else:
                    self._known[value] = "PII"
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            lower = normalize_key(key)
            if lower in SECRET_KEYS_NORMALIZED:
                self._known[str(value)] = "SECRET"
            elif lower in PII_KEYS_NORMALIZED:
                self._known[str(value)] = "PII"

    def _mask_value(self, key: str | None, value: Any) -> Any:
        if isinstance(value, dict):
            return {item_key: self._mask_value(str(item_key), item) for item_key, item in value.items()}
        if isinstance(value, list):
            return [self._mask_value(key, item) for item in value]
        if isinstance(value, str):
            if is_secret_key(key):
                return self._placeholder("SECRET", value)
            masked = self._mask_text(value)
            if is_pii_key(key) and masked == value and value:
                return self._placeholder("PII", value)
            return masked
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if is_secret_key(key) or is_pii_key(key):
                kind = "SECRET" if is_secret_key(key) else "PII"
                return self._placeholder(kind, str(value))
        return value

    def apply(self, payload: Any) -> MaskingResult:
        # 同一 policy 会被三路盲评/投票并发调用；apply 内部状态必须串行
        with self._lock:
            self.counts = {}
            self._mapping = {}
            self._counters = {}
            self._known = {}
            self._collect(None, payload)
            masked = self._mask_value(None, copy.deepcopy(payload))
            report = {
                "policy_id": self.policy_id,
                "version": self.version,
                "applied": True,
                "counts": dict(self.counts),
                "total": sum(self.counts.values()),
            }
            return MaskingResult(data=masked, report=report)
