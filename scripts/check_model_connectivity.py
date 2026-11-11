"""模型连通性与能力冒烟（V-01 准入的最小实测）。

逐个角色读取 `config/models.yaml`，用真实供应商接口发一个最小 JSON 请求，记录：
状态码、延迟、返回的模型版本、token 用量、JSON 是否可解析。
不打印密钥；可输出 JSON 供证据归档。

用法：
    python scripts/check_model_connectivity.py
    python scripts/check_model_connectivity.py --json evidence/V-01/model-smoke.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.llm.adapters.chat import OpenAICompatibleChatAdapter  # noqa: E402
from app.llm.base import AdapterError, ChatMessage, ChatRequest, parse_json_object  # noqa: E402
from app.llm.factory import build_chat_adapter  # noqa: E402
from app.llm.registry import ModelRegistry  # noqa: E402

DEFAULT_ROLES = ("chief_blind", "jury_a", "jury_b")


async def check_role(
    registry: ModelRegistry, role: str, environ: dict[str, str]
) -> dict:
    config = registry.role(role)
    adapter: OpenAICompatibleChatAdapter = build_chat_adapter(
        registry, role, environ=environ
    )
    request = ChatRequest(
        messages=[
            ChatMessage(
                role="system",
                content="你是模型连通性检查助手。只输出一个 JSON 对象，不要解释。",
            ),
            ChatMessage(
                role="user",
                content='返回 {"ok": true, "role": "connectivity"}，不要 markdown。',
            ),
        ],
        temperature=config.temperature,
        max_tokens=config.max_output_tokens,
        response_format={"type": "json_object"},
    )
    started = time.perf_counter()
    result: dict = {
        "role": role,
        "provider": config.provider,
        "model_id": config.model_id,
        "status": "failed",
    }
    try:
        response = await adapter.complete(request)
        latency_ms = int((time.perf_counter() - started) * 1000)
        payload = parse_json_object(response.text)
        result.update(
            {
                "status": "ok",
                "returned_model": response.model,
                "latency_ms": latency_ms,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "json_ok": payload.get("ok") is True,
                "content_length": len(response.text),
            }
        )
    except AdapterError as exc:
        result.update(
            {
                "status": "failed",
                "error_code": exc.code,
                "retryable": exc.retryable,
                "status_code": exc.status_code,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        )
    finally:
        await adapter.aclose()
    return result


async def main() -> int:
    parser = argparse.ArgumentParser(description="模型连通性冒烟")
    parser.add_argument("--roles", default=",".join(DEFAULT_ROLES))
    parser.add_argument("--json", help="输出 JSON 结果路径")
    args = parser.parse_args()

    registry = ModelRegistry.load(ROOT / "config" / "models.yaml")
    environ = dict(os.environ)
    roles = [role.strip() for role in args.roles.split(",") if role.strip()]
    results = [await check_role(registry, role, environ) for role in roles]

    for item in results:
        if item["status"] == "ok":
            print(
                f"[OK] {item['role']:12} {item['provider']}/{item['model_id']} "
                f"latency={item['latency_ms']}ms tokens={item['input_tokens']}+{item['output_tokens']} "
                f"json={item['json_ok']}"
            )
        else:
            print(
                f"[FAIL] {item['role']:12} {item['provider']}/{item['model_id']} "
                f"code={item.get('error_code')} retryable={item.get('retryable')}"
            )

    payload = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "registry_version": registry.version,
        "results": results,
    }
    if args.json:
        target = Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"written {target}")
    return 0 if all(item["status"] == "ok" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
