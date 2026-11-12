from app.core.auth import Principal
from app.core.enums import ActorType
from app.llm.mock import MockChatClient
from app.main import create_app
from tests.helpers import make_settings, review_payload, valid_case


async def test_dual_topology_freezes_two_roles_and_never_calls_third_model():
    app = create_app(make_settings(review_topology="dual"), run_worker=False)

    class TwoModels(MockChatClient):
        reviews = []
        votes = []

        async def review(self, role, case):
            assert role in {"chief_blind", "jury_a"}
            self.reviews.append(role)
            return await super().review(role, case)

        async def vote(self, role, material):
            assert role in {"chief_blind", "jury_a"}
            self.votes.append(role)
            return await super().vote(role, material)

    model = TwoModels()
    app.state.pipeline.model = model
    actor = Principal("dual-test", ActorType.SERVICE, frozenset({"reviewer"}), None)
    case = valid_case(steps=[{"index": 1, "action": "提交", "expected": None}])
    submitted = await app.state.review_service.submit(review_payload(case), actor)
    # A later default change must not add a third reviewer to this task.
    app.state.pipeline.settings.review_topology = "multi"
    assert await app.state.worker.run_once() == "done"
    job = await app.state.storage.get_job(submitted.body["review_id"])
    assert job.topology_snapshot["roles"] == ["chief_blind", "jury_a"]
    assert set(model.reviews) == set(model.votes) == {"chief_blind", "jury_a"}
    assert job.report_json["topology"] == "dual"
    assert job.report_json["review_completeness"]["blind"] == "2/2"
    assert job.report_json["review_completeness"]["vote"] == "2/2"
    assert "model_missing" not in job.report_json["degraded_reasons"]
