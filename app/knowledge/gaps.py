"""Suspected evidence gaps derived from immutable reports; never auto-admit model claims."""
from __future__ import annotations

from app.knowledge.runtime import digest


def report_gaps(case: dict, issues: list[dict], *, covered: bool) -> list[dict]:
    gaps = []
    seen = set()
    for issue in issues:
        state = issue.get("evidence_status")
        if issue.get("dimension") != "business" or state not in {"ungrounded", "insufficient", "conflicted"}:
            continue
        question = "待核实证据：" + str(issue.get("rationale") or "业务依据不充分")
        if question in seen:
            continue
        seen.add(question)
        gaps.append({"module": str(case.get("module") or "unknown"),
                     "function_point": str(case.get("title") or "未指定"),
                     "suspected_rule": question, "occurrences": 1, "status": "open",
                     "gap_type": "knowledge_conflict" if state == "conflicted"
                     else "retrieval_missed" if covered else "knowledge_missing"})
    return gaps


async def aggregate_gaps(storage, project: str, *, limit: int = 500) -> dict:
    jobs = await storage.list_jobs(limit=limit + 1)
    grouped = {}
    for job in jobs[:limit]:
        report = job.report_json
        if not report:
            continue
        case = report.get("appendix", {}).get("normalized_case", {})
        if case.get("project_id") != project:
            continue
        pack = report.get("appendix", {}).get("knowledge_pack") or {}
        baseline = case.get("review_baseline")
        gaps = report.get("kb_gaps") or report_gaps(case, report.get("issues", []), covered=bool(pack.get("evidence")))
        for gap in gaps:
            key = digest([project, baseline, gap["module"], gap["function_point"], gap["suspected_rule"]])
            item = grouped.setdefault(key, {**gap, "gap_id": key, "project_id": project, "baseline": baseline,
                                             "occurrences": 0, "examples": [], "knowledge_versions": []})
            item["occurrences"] += 1
            item["examples"].append({"review_id": job.id, "case_id": job.case_id, "generation": job.generation})
            version = job.kb_build_version
            if version not in item["knowledge_versions"]:
                item["knowledge_versions"].append(version)
    return {"items": sorted(grouped.values(), key=lambda x: (-x["occurrences"], x["gap_id"])),
            "scanned_reviews": min(limit, len(jobs)), "truncated": len(jobs) > limit, "hypotheses_only": True,
            "note": "这是待复核证据线索，不能直接当作业务规则或自动进入知识库。"}
