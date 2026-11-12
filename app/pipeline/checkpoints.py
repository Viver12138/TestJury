"""Reuse complete outputs only for identical task, upstream inputs and runtime versions."""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.core.state_machine import FencingMismatch
from app.knowledge.runtime import digest


class Checkpoints:
    def __init__(self, storage, job, versions):
        self.storage, self.job = storage, job
        # A deployment changing pipeline/model parsing must not reuse a stale output.
        app = Path(__file__).resolve().parents[1]
        implementation = digest({p.relative_to(app).as_posix(): p.read_text(encoding="utf-8")
                                 for folder in ("pipeline", "llm") for p in (app / folder).rglob("*.py")})
        self.scope = {"case": job.normalized_case, "generation": job.generation,
                      "snapshot": job.topology_snapshot, "kb": job.kb_build_version,
                      "versions": versions.report_versions(), "implementation": implementation,
                      "schema": job.report_schema_version}
        self.reused: list[str] = []

    async def run(self, key: str, inputs: dict, operation: Callable[[], Awaitable[dict]],
                  *, reusable: Callable[[dict], bool] | None = None) -> dict:
        current = await self.storage.get_job(self.job.id)
        if current is None or current.status != "processing" or current.fencing_token != self.job.fencing_token:
            raise FencingMismatch(self.job.fencing_token, current.fencing_token if current else -1)
        input_hash = digest({"scope": self.scope, "stage": key, "inputs": inputs})
        saved = await self.storage.get_checkpoint(self.job.id, key, input_hash)
        if saved is not None:
            if saved["output_digest"] != digest(saved["payload"]):
                raise RuntimeError("checkpoint integrity check failed")
            self.reused.append(key)
            return saved["payload"]
        result = json.loads(json.dumps(await operation(), ensure_ascii=False, default=str))
        if reusable is None or reusable(result):
            await self.storage.put_checkpoint(self.job.id, key, input_hash, result, digest(result), self.job.fencing_token)
        return result
