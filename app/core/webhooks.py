"""Signed summary-only notifications; DNS is validated and the connection is pinned."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
from urllib.parse import urlsplit

import httpx


def validate_webhook_url(url, settings) -> str:
    if not settings.webhook_enabled:
        raise ValueError("完成通知尚未启用")
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("完成通知地址格式不合法")
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").encode("idna").decode("ascii").lower()
        allowed = {h.strip().lower() for h in settings.webhook_allowed_hosts.split(",") if h.strip()}
        if (parts.scheme != "https" or not host or parts.port not in (None, 443)
                or parts.username or parts.password or parts.fragment or host not in allowed):
            raise ValueError("完成通知只接受已配置允许列表中的 HTTPS 地址")
    except (UnicodeError, ValueError) as exc:
        raise ValueError("完成通知只接受已配置允许列表中的 HTTPS 地址") from exc
    return host


async def deliver(event, settings, *, transport=None, resolver=None):
    host = validate_webhook_url(event["url"], settings)
    if resolver is None:
        addresses = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ips = {row[4][0] for row in addresses}
    else:
        ips = set(await resolver(host))
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError("完成通知地址解析到受限网络，未发送")
    content = json.dumps(event["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    stamp = str(int(time.time()))
    signature = hmac.new(settings.webhook_secret.encode(), stamp.encode() + b"." + content, hashlib.sha256).hexdigest()
    pinned = httpx.URL(event["url"]).copy_with(host=sorted(ips)[0])
    # Each delivery has its own pool: a connection authenticated for one hostname
    # cannot be reused for another allowed hostname sharing the same IP.
    async with httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False,
                                 timeout=settings.webhook_timeout_seconds) as client:
        async with client.stream("POST", pinned, content=content,
                                 headers={"Host": host, "Content-Type": "application/json",
                                          "X-Event-Id": event["event_id"], "X-Timestamp": stamp,
                                          "X-Signature": "sha256=" + signature},
                                 extensions={"sni_hostname": host}) as response:
            if not 200 <= response.status_code < 300:
                raise ValueError("callback_http_" + str(response.status_code))


class WebhookWorker:
    def __init__(self, storage, settings, *, sender=deliver):
        self.storage, self.settings, self.sender = storage, settings, sender
        self.task = None

    async def run_once(self):
        await self.storage.enqueue_webhooks()
        event = await self.storage.claim_webhook(self.settings.webhook_timeout_seconds + 30,
                                                self.settings.webhook_max_retries)
        if event is None:
            return None
        try:
            await asyncio.wait_for(self.sender(event, self.settings), self.settings.webhook_timeout_seconds)
        except (httpx.HTTPError, ValueError, OSError, TimeoutError) as exc:
            # Do not retain remote response bodies, URLs or exception messages.
            await self.storage.finish_webhook(event["event_id"], event["attempts"], False,
                                               min(300, 2 ** event["attempts"]),
                                               self.settings.webhook_max_retries, type(exc).__name__)
            logging.getLogger("testjury.webhook").warning("callback_delivery_failed event=%s attempt=%s",
                                                         event["event_id"], event["attempts"])
            return "failed_attempt"
        await self.storage.finish_webhook(event["event_id"], event["attempts"], True, 0,
                                           self.settings.webhook_max_retries, None)
        return "delivered"

    async def _loop(self):
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.getLogger("testjury.webhook").error("callback_worker_error")
            await asyncio.sleep(2)

    def start(self):
        if self.task is None:
            self.task = asyncio.create_task(self._loop())

    async def stop(self):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
