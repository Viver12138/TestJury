"""Reserve conservatively before each paid attempt; uncertain calls keep their reservation."""
from __future__ import annotations

import math
from contextvars import ContextVar

from app.llm.base import AdapterError
from app.storage.models import new_id

active_budget: ContextVar[ModelBudget | None] = ContextVar("active_budget", default=None)


class ModelBudget:
    def __init__(self, storage, job, settings):
        self.storage, self.job = storage, job
        frozen = job.topology_snapshot.get("budget") or {}
        requested = (job.request_payload.get("options") or {}).get("budget_tokens")
        self.limits = {"review_tokens": min(settings.review_budget_tokens, frozen.get("review_tokens", requested or
                                                                                     settings.review_budget_tokens)),
                       "review_cost": min(settings.review_budget_cost,
                                          frozen.get("review_cost", settings.review_budget_cost)),
                       "batch_cost": min(settings.batch_budget_cost, frozen.get("batch_cost", settings.batch_budget_cost)),
                       "daily_cost": min(settings.daily_budget_cost, frozen.get("daily_cost", settings.daily_budget_cost))}
        self.exhausted = False

    async def reserve(self, request, config, pricing):
        prices = pricing.get(config.model_id)
        if not isinstance(prices, dict) or any(k not in prices for k in ("input_per_1k", "output_per_1k")):
            raise AdapterError("BUDGET_UNAVAILABLE", "模型缺少费用估算配置，未发起调用", retryable=False)
        rates = [float(prices[k]) for k in ("input_per_1k", "output_per_1k")]
        if any(not math.isfinite(x) or x < 0 for x in rates):
            raise AdapterError("BUDGET_UNAVAILABLE", "费用估算配置非法，未发起调用", retryable=False)
        # UTF-8 byte count + message overhead is deliberately conservative. This is
        # an admission bound, not a claim to know a provider's private tokenizer/bill.
        input_bound = sum(len(m.content.encode("utf-8")) + 64 for m in request.messages) + 256
        output_bound = request.max_tokens or config.max_output_tokens
        reservation = {"id": new_id(), "model": config.model_id,
                       "tokens_reserved": input_bound + output_bound,
                       "cost_reserved": (input_bound * rates[0] + output_bound * rates[1]) / 1000}
        accepted = await self.storage.reserve_model_budget(self.job.id, self.job.fencing_token,
                                                           reservation, self.limits)
        if not accepted:
            self.exhausted = True
            raise AdapterError("BUDGET_EXCEEDED", "剩余预算不足以覆盖本次调用，未发起供应商请求", retryable=False)
        return reservation["id"], rates

    async def settle(self, reservation, response):
        ident, rates = reservation
        usage = response.usage
        # Missing/zero usage does not prove the call was free. Leave its full reserve.
        if usage.input_tokens > 0 and usage.output_tokens >= 0:
            await self.storage.settle_model_budget(ident, usage.total,
                (usage.input_tokens * rates[0] + usage.output_tokens * rates[1]) / 1000)

    async def summary(self):
        rows = await self.storage.list_model_budget(self.job.id)
        return {"limits": self.limits, "exhausted": self.exhausted,
                "accounted_tokens": sum(r["tokens_actual"] if r["status"] == "settled"
                                        else r["tokens_reserved"] for r in rows),
                "estimated_cost": sum(float(r["cost_actual"] if r["status"] == "settled"
                                            else r["cost_reserved"]) for r in rows),
                "uncertain_calls": sum(r["status"] != "settled" for r in rows),
                "scope": "chat requests; conservative reservations, configured estimated prices; not provider billing"}
