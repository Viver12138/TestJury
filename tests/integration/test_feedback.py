import copy

import pytest

from app.core.auth import Principal
from app.core.enums import ActorType
from app.core.errors import ApiError
from app.main import create_app
from app.services.feedback import FeedbackService
from tests.helpers import make_settings, review_payload


async def test_feedback_preserves_history_identity_and_report():
    app = create_app(make_settings())
    actor = Principal("delegated-reviewer", ActorType.SERVICE, frozenset({"reviewer"}), None)
    submitted = await app.state.review_service.submit(review_payload(), actor)
    ident = submitted.body["review_id"]
    feedback = FeedbackService(app.state.storage)
    body = {"issues": [{"verdict": "missed", "step_index": 1, "severity": "major", "note": "具体漏检说明"}]}
    with pytest.raises(ApiError):
        await feedback.submit(ident, body, actor)
    await app.state.worker.run_once()
    before = copy.deepcopy((await app.state.storage.get_job(ident)).report_json)
    first = await feedback.submit(ident, body, actor)
    second = await feedback.submit(ident, body, actor)
    assert first["feedback_id"] != second["feedback_id"]
    assert first["reviewer"] == actor.actor_id
    assert first["annotation_type"] == "service_feedback"
    assert first["gold_admission"] == "not_admitted"
    assert len((await feedback.list(ident, actor))["items"]) == 2
    assert (await app.state.storage.get_job(ident)).report_json == before
    assert (await app.state.storage.get_job(ident)).human_status == "pending"
    for invalid in ({**body, "reviewer": "forged-human"},
                    {"issues": [{"verdict": "adopted", "issue_no": 999, "note": "不存在"}]},
                    {"issues": [{"verdict": "missed", "step_index": 999, "severity": "major", "note": "不存在"}]}):
        with pytest.raises(ApiError):
            await feedback.submit(ident, invalid, actor)


@pytest.mark.postgres
async def test_feedback_identifier_and_provenance_survive_database_reload(migrated_database):
    app = create_app(make_settings(storage_backend="postgres", database_url=migrated_database))
    actor = Principal("delegated-reviewer", ActorType.SERVICE, frozenset({"reviewer"}), None)
    try:
        submitted = await app.state.review_service.submit(review_payload(), actor)
        await app.state.worker.run_once()
        service = FeedbackService(app.state.storage)
        saved = await service.submit(submitted.body["review_id"], {"issues": [
            {"verdict": "missed", "step_index": 1, "severity": "major", "note": "代理技术复核"}]}, actor)
        reloaded = (await service.list(submitted.body["review_id"], actor))["items"][0]
        assert reloaded["feedback_id"] == saved["feedback_id"]
        assert reloaded["actor_type"] == "service"
        assert reloaded["versions"] == saved["versions"]
    finally:
        await app.state.storage.close()
