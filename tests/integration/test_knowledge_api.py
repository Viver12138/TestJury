import json

from fastapi.testclient import TestClient

from app.main import create_app
from tests.helpers import REVIEWER_KEY, auth_headers, bootstrap_keys, make_settings
from tests.unit.test_knowledge_runtime import acceptance, prepared


async def test_publication_uses_server_proof_and_separate_role(tmp_path):
    keys = json.loads(bootstrap_keys())
    keys.append({"key": "publisher-test-key-1234", "actor_id": "publisher", "actor_type": "service",
                 "roles": ["kb_publisher"]})
    app = create_app(make_settings(knowledge_enabled=True, knowledge_acceptance_dir=tmp_path,
                                   knowledge_delegated_acceptance=True, bootstrap_api_keys=json.dumps(keys)))
    service, release = await prepared()
    app.state.knowledge = service
    payload = {"version": release["version"], "expected_active_version": None, "reason": "tested"}
    publisher = auth_headers("publisher-test-key-1234")
    with TestClient(app) as client:
        assert client.post("/v1/knowledge/activate", json=payload).status_code == 401
        assert client.post("/v1/knowledge/activate", json=payload,
                           headers=auth_headers(REVIEWER_KEY)).status_code == 403
        # Client-supplied acceptance cannot replace trusted server evidence.
        assert client.post("/v1/knowledge/activate", json={**payload, "acceptance": acceptance(release)},
                           headers=publisher).status_code == 422
        path = tmp_path / (release["version"] + ".json")
        path.write_text(json.dumps({**acceptance(release), "passed": False}), encoding="utf-8")
        assert client.post("/v1/knowledge/activate", json=payload, headers=publisher).status_code == 409
        path.write_text(json.dumps(acceptance(release)), encoding="utf-8")
        assert client.post("/v1/knowledge/activate", json=payload, headers=publisher).status_code == 200
        assert client.post("/v1/knowledge/activate", json=payload, headers=publisher).status_code == 409
        result = client.get("/v1/knowledge/minishop/status", headers=auth_headers()).json()
        assert result["active_version"] == release["version"]
        assert len(result["history"]) == 1
        assert client.get("/v1/knowledge/minishop/gaps").status_code == 401
        gaps = client.get("/v1/knowledge/minishop/gaps", headers=auth_headers()).json()
        assert gaps["hypotheses_only"] is True
        assert gaps["items"] == []
