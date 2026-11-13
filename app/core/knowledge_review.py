"""Describe the evidence actually available to a review, including historical reports."""

from __future__ import annotations

from typing import Any

GENERAL_MESSAGE = "知识库中没有可用于本次用例的相关知识，已降级为通用评审；仅检查用例质量，未验证产品业务规则。"
EMPTY_MESSAGE = "知识库已启用，但本次未检索到相关知识，已降级为通用评审；未验证产品业务规则。"


def knowledge_review(report: dict[str, Any] | None, *, frozen_version: str | None = None) -> dict[str, Any]:
    report = report or {}
    pack = (report.get("appendix") or {}).get("knowledge_pack")
    evidence = (pack or {}).get("evidence") or []
    reasons = report.get("degraded_reasons") or []
    if "kb_module_missing" in reasons or (not report and frozen_version == "kb-none"):
        return {"mode": "general", "label": "通用评审（已降级）", "knowledge_available": False,
                "evidence_count": 0, "message": EMPTY_MESSAGE if pack else GENERAL_MESSAGE}
    if evidence:
        return {"mode": "knowledge", "label": "知识库辅助评审", "knowledge_available": True,
                "evidence_count": len(evidence), "message": f"本次评审引用了 {len(evidence)} 条知识依据。"}
    if not report:
        return {"mode": "pending", "label": "知识检索待完成", "knowledge_available": None,
                "evidence_count": 0, "message": "知识覆盖情况将在评审中确认。"}
    return {"mode": "unrecorded", "label": "未记录知识依据", "knowledge_available": False,
            "evidence_count": 0, "message": "该报告未记录可用知识依据，不能视为已验证产品业务规则。"}
