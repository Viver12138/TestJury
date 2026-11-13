from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.core.auth import Principal
from app.core.enums import ActorType
from app.core.errors import ApiError
from app.core.knowledge_review import GENERAL_MESSAGE
from app.knowledge.runtime import index_candidate
from app.main import create_app
from tests.helpers import make_settings, valid_case
from tests.unit.test_knowledge_runtime import acceptance, candidate


async def prepared(platforms=None):
    app = create_app(make_settings(knowledge_enabled=True, review_topology="dual"), run_worker=False)
    data = candidate()
    if platforms:
        data["chunks"][0]["platforms"] = platforms
    release = await index_candidate(data)
    await app.state.knowledge.store.put(release)
    await app.state.knowledge.publish(release["version"], actor="test", reason="test", expected=None,
                                     acceptance=acceptance(release), allow_delegated=True)
    principal = Principal("test", ActorType.SERVICE, frozenset({"reviewer"}), None)
    return app, principal


def case(identifier, module="login", **patch):
    return valid_case(identifier, module=module, project_id="minishop", product_version="1.0.0",
                      review_baseline="current_implementation",
                      title="服务端金额 SKU 价格" if module == "order" else "登录流程",
                      **patch)


@pytest.mark.asyncio
async def test_mixed_batch_falls_back_per_case_and_marks_json_markdown_excel():
    app, principal = await prepared()
    payload = {"cases": [case("LOGIN-1"), case("ORDER-1", "order")], "options": {"strict_kb": False}}
    status, result = await app.state.batch_service.create(payload, principal)
    assert status == 202
    detail = await app.state.batch_service.get(result["batch_id"])
    planned = {x["case_id"]: x["knowledge_review"]["mode"] for x in detail["items"]}
    assert planned == {"LOGIN-1": "general", "ORDER-1": "pending"}
    for _ in range(2):
        assert await app.state.worker.run_once() in {"done", "completed_with_warnings"}
    jobs = await app.state.storage.list_jobs(batch_id=result["batch_id"], limit=10)
    report_by_id = {x.case_id: x.report_json for x in jobs}
    generic = report_by_id["LOGIN-1"]
    assert generic["degraded"] and "kb_module_missing" in generic["degraded_reasons"]
    assert generic["appendix"]["knowledge_review"]["mode"] == "general"
    assert generic["versions"]["kb_build_version"] == "kb-none"
    assert all(not issue["kb_grounded"] for issue in generic["issues"])
    assert report_by_id["ORDER-1"]["appendix"]["knowledge_review"]["mode"] == "knowledge"
    assert report_by_id["ORDER-1"]["appendix"]["knowledge_pack"]["evidence"]
    login_job = next(x for x in jobs if x.case_id == "LOGIN-1")
    assert GENERAL_MESSAGE in await app.state.review_service.markdown(login_job.id)
    from app.services.excel_report import render_excel

    book = load_workbook(BytesIO(render_excel(jobs)))
    rows = list(book["评审汇总"].values)
    records = [dict(zip(rows[0], row, strict=True)) for row in rows[1:]]
    exported = next(x for x in records if x["用例编号"] == "LOGIN-1")
    assert exported["评审方式"] == "通用评审（已降级）"
    assert GENERAL_MESSAGE == exported["知识覆盖说明"]
    assert any(row[-1] == GENERAL_MESSAGE for row in book["知识依据"].values)
    repeated, replay = await app.state.batch_service.create(payload, principal)
    assert repeated == 200 and replay["batch_id"] == result["batch_id"]


@pytest.mark.asyncio
async def test_explicit_strict_api_still_rejects_missing_knowledge_atomically():
    app, principal = await prepared()
    with pytest.raises(ApiError, match="没有已启用知识"):
        await app.state.batch_service.create({"cases": [case("ORDER-1", "order"), case("LOGIN-1")],
                                             "options": {"strict_kb": True}}, principal)
    assert await app.state.storage.list_jobs(limit=10) == []


@pytest.mark.asyncio
async def test_enabled_build_with_no_matching_evidence_is_marked_general():
    app, principal = await prepared(["api"])
    item = case("ORDER-MOBILE", "order")
    item["platform"] = "mobile"  # The test release only covers API.
    submitted = await app.state.review_service.submit({"case": item}, principal)
    assert await app.state.worker.run_once() in {"done", "completed_with_warnings"}
    job = await app.state.storage.get_job(submitted.body["review_id"])
    report = job.report_json
    assert report["appendix"]["knowledge_pack"]["evidence"] == []
    assert report["appendix"]["knowledge_review"]["mode"] == "general"
    assert "未检索到相关知识" in report["appendix"]["knowledge_review"]["message"]


@pytest.mark.asyncio
async def test_none_knowledge_snapshot_does_not_switch_to_later_published_release():
    app, principal = await prepared()
    item = case("LOGIN-FROZEN")
    submitted = await app.state.review_service.submit({"case": item}, principal)
    changed = candidate()
    changed["chunks"][0]["module"] = "login"
    release = await index_candidate(changed)
    await app.state.knowledge.store.put(release)
    old = await app.state.knowledge.store.current("minishop", "current_implementation")
    await app.state.knowledge.publish(release["version"], actor="test", reason="new", expected=old["version"],
                                     acceptance=acceptance(release), allow_delegated=True)
    assert await app.state.knowledge.resolve("minishop", "current_implementation", "login")
    assert await app.state.worker.run_once() in {"done", "completed_with_warnings"}
    job = await app.state.storage.get_job(submitted.body["review_id"])
    assert job.report_json["versions"]["kb_build_version"] == "kb-none"
    assert job.report_json["appendix"]["knowledge_review"]["mode"] == "general"
