from types import SimpleNamespace

from app.knowledge.gaps import aggregate_gaps, report_gaps


async def test_gap_hypotheses_are_scoped_and_do_not_mutate_reports():
    issue = {"dimension": "business", "evidence_status": "insufficient", "rationale": "券是否可以叠加"}
    case = {"project_id": "minishop", "module": "order", "title": "用券", "review_baseline": "current_implementation"}
    report = {"issues": [issue], "appendix": {"normalized_case": case}}
    job = SimpleNamespace(report_json=report, id="r1", case_id="c1", generation=1, kb_build_version="kb-none")

    class Store:
        async def list_jobs(self, **kwargs):
            return [job]

    assert (await aggregate_gaps(Store(), "other"))["items"] == []
    result = await aggregate_gaps(Store(), "minishop")
    assert result["hypotheses_only"] is True
    assert result["items"][0]["status"] == "open"
    assert result["items"][0]["examples"][0]["review_id"] == "r1"
    assert "kb_gaps" not in report
    assert report_gaps(case, [{**issue, "evidence_status": "grounded"}], covered=True) == []
    assert report_gaps(case, [{**issue, "dimension": "test_design"}], covered=False) == []
