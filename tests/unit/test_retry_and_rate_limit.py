"""Retry 接入、取消、限流竞态（不调用供应商）。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest
import yaml

from app.llm.attempts import attempt_log
from app.llm.base import AdapterError, ChatResponse, TokenUsage
from app.llm.registry import ModelRegistry
from app.llm.retry import call_with_retry
from app.llm.review import ChatReviewModel
from app.pipeline.vote import run_vote
from app.rubric.loader import RubricRepository
from app.storage.models import CandidateRecord

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS = REPO_ROOT / "config" / "models.yaml"


def _review_json() -> str:
    return json.dumps({"overall": {"comment": "ok"}, "issues": []}, ensure_ascii=False)


class RecordingAdapter:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[float] = []

    async def complete(self, request):
        self.calls.append(time.perf_counter())
        if self.failures:
            self.failures -= 1
            raise AdapterError("RATE_LIMITED", "429", retryable=True, status_code=429)
        return ChatResponse(
            text=_review_json(),
            model="fake-model",
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            latency_ms=7,
            raw={"id": "fake"},
        )

    async def aclose(self) -> None:
        return None


def _model(tmp_path: Path, adapter, *, role: str = "jury_a", interval: float = 0.0, max_attempts: int = 3):
    payload = yaml.safe_load(MODELS.read_text(encoding="utf-8"))
    for spec in payload["roles"].values():
        spec["min_interval_seconds"] = 0
    payload["roles"][role]["min_interval_seconds"] = interval
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    registry = ModelRegistry.load(path)
    rubric = RubricRepository(
        REPO_ROOT / "rubric" / "rubric.yaml", REPO_ROOT / "rubric" / "schema.json"
    ).load_active()
    return ChatReviewModel(
        registry,
        {role: adapter},
        rubric=rubric,
        max_attempts=max_attempts,
        base_delay=0.01,
        jitter=0,
    )


@pytest.mark.asyncio
async def test_retry_is_wired_into_complete(tmp_path: Path) -> None:
    adapter = RecordingAdapter(failures=2)
    model = _model(tmp_path, adapter, max_attempts=3)
    opinion = await model.review("jury_a", {"case_id": "TC-1", "steps": []})
    assert len(adapter.calls) == 3
    assert len(opinion.attempts) == 3
    assert opinion.attempts[0]["error_code"] == "RATE_LIMITED"
    assert opinion.attempts[-1]["status"] == "ok"
    assert opinion.request_hash and opinion.response_hash


@pytest.mark.asyncio
async def test_non_retryable_error_is_not_retried(tmp_path: Path) -> None:
    class FatalAdapter(RecordingAdapter):
        async def complete(self, request):
            self.calls.append(time.perf_counter())
            raise AdapterError("PROVIDER_REJECTED", "400", retryable=False)

    adapter = FatalAdapter()
    model = _model(tmp_path, adapter)
    with pytest.raises(AdapterError):
        await model.review("jury_a", {"case_id": "TC-1", "steps": []})
    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_rate_limit_interval_is_checked_inside_semaphore(tmp_path: Path) -> None:
    adapter = RecordingAdapter()
    model = _model(tmp_path, adapter, role="jury_b", interval=0.06)
    await asyncio.gather(
        model.review("jury_b", {"case_id": "TC-1", "steps": []}),
        model.review("jury_b", {"case_id": "TC-2", "steps": []}),
    )
    assert len(adapter.calls) == 2
    assert adapter.calls[1] - adapter.calls[0] >= 0.05


@pytest.mark.asyncio
async def test_cancel_propagates_during_backoff() -> None:
    started = asyncio.Event()

    async def operation():
        started.set()
        raise AdapterError("RATE_LIMITED", "429", retryable=True)

    task = asyncio.create_task(
        call_with_retry(operation, base_delay=10, jitter=0)
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_attempt_hook_records_retry_and_success() -> None:
    attempts: list[tuple[int, str | None, float]] = []

    async def operation():
        if len(attempts) == 0:
            raise AdapterError("PROVIDER_UNAVAILABLE", "5xx", retryable=True)
        return "ok"

    result = await call_with_retry(
        operation,
        base_delay=0.01,
        jitter=0,
        on_attempt=lambda number, error, delay: attempts.append(
            (number, error.code if error else None, delay)
        ),
    )
    assert result == "ok"
    assert attempts[0][0] == 1 and attempts[0][1] == "PROVIDER_UNAVAILABLE"
    assert attempts[1] == (2, None, 0.0)


@pytest.mark.asyncio
async def test_vote_timeout_keeps_started_attempt_audit() -> None:
    class HangingModel:
        async def vote(self, role, material):
            audit = attempt_log.get()
            assert audit is not None
            audit.append(
                {
                    "attempt": 1,
                    "status": "started",
                    "error_code": None,
                    "retryable": None,
                    "delay_s": None,
                    "latency_ms": None,
                }
            )
            await asyncio.sleep(1)

        async def review(self, role, case):  # pragma: no cover
            raise AssertionError

    candidate = CandidateRecord(
        id="c-timeout",
        review_id="r1",
        candidate_no=1,
        dimension="test_design",
        standardized_text="第 1 步缺预期",
        step_index=1,
        category="预期不明确",
    )
    votes, calls = await run_vote(
        "r1", [candidate], HangingModel(), ["jury_a"], timeout_seconds=0.01
    )
    assert votes[0].validity == "not_assessed"
    assert calls[0]["error_code"] == "MODEL_TIMEOUT"
    assert calls[0]["attempts"][0]["status"] == "started"


@pytest.mark.asyncio
async def test_vote_does_not_add_second_retry_layer() -> None:
    class FailingModel:
        def __init__(self) -> None:
            self.calls = 0

        async def vote(self, role, material):
            self.calls += 1
            raise AdapterError("RATE_LIMITED", "429", retryable=True)

        async def review(self, role, case):  # pragma: no cover - protocol completeness
            raise AssertionError

    model = FailingModel()
    candidate = CandidateRecord(
        id="c1",
        review_id="r1",
        candidate_no=1,
        dimension="test_design",
        standardized_text="第 1 步缺预期",
        step_index=1,
        category="预期不明确",
    )
    votes, calls = await run_vote("r1", [candidate], model, ["jury_a"], timeout_seconds=5)
    assert model.calls == 1  # 外层不得再次重试
    assert votes[0].validity == "not_assessed"
    assert calls[0]["error_code"] == "RATE_LIMITED"


