"""Markdown 报告渲染（docs/03 §3）：只读 `report_json`，不重新计算结论。

文案约束：AI 结论不得写成"通过/合格"，人工审批不得被写成"用例通过"。
"""

from __future__ import annotations

from typing import Any

VERDICT_LABELS = {
    "blocked": "存在阻断问题（blocked）",
    "conditional": "有条件可用（conditional）",
    "need_human": "需人工判断（need_human）",
    None: "未形成正式 AI 结论",
}

HUMAN_LABELS = {
    "pending": "待人工审批（pending）",
    "approved": "人工已确认（approved）",
    "rejected": "人工已驳回（rejected）",
    "changes_requested": "人工要求修改后重提（changes_requested）",
}

REASON_LABELS = {
    "partially_grounded_blocker": "blocker 证据部分支持，待人工确认",
    "blocker_in_partial_review": "部分模型参与下的 blocker，需人工复核",
    "validity_disputed": "成立性存在分歧",
    "severity_disputed": "严重级跨两级分歧",
    "evidence_conflict": "证据冲突",
}


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    verdict = report.get("ai_verdict")
    lines.append(f"# 评审报告 · {report.get('case_id')}")
    lines.append("")
    lines.append(f"- 评审 ID：`{report.get('review_id')}`")
    lines.append(f"- AI 结论：**{VERDICT_LABELS.get(verdict, verdict)}**")
    lines.append(f"- 人工状态：{HUMAN_LABELS.get(report.get('human_status'), report.get('human_status'))}")
    lines.append(f"- 报告版本：`{report.get('report_schema_version')}`")
    versions = report.get("versions") or {}
    lines.append(
        f"- 版本：rubric `{versions.get('rubric')}` · KB `{versions.get('kb_build_version')}`"
        f" · prompts `{versions.get('prompts')}`"
    )
    degraded = report.get("degraded_reasons") or []
    lines.append(f"- 降级/限制：{', '.join(degraded) if degraded else '无'}")
    completeness = report.get("review_completeness") or {}
    lines.append(
        f"- 评审完整性：complete={str(completeness.get('complete')).lower()}"
        f" · 参与度 blind={completeness.get('blind')} vote={completeness.get('vote')}"
        f" · full_participation={str(completeness.get('full_participation')).lower()}"
    )
    lines.append("")
    lines.append(
        "> AI 结论不是审批结论：AI 未发现问题不等于用例合格；"
        "知识库无规则不等于业务规则不存在；报告生成成功不等于人工审批完成。"
    )
    knowledge = (report.get("appendix") or {}).get("knowledge_pack")
    if knowledge:
        lines.append("")
        lines.append(f"评审基线：`{knowledge['baseline']['type']}`；知识证据：{len(knowledge['evidence'])} 条。")
        lines.append("")
        for item in knowledge["evidence"]:
            lines.append(f"- `{item['chunk_id']}` · {item['doc_id']} · {item['heading_path']} · {item['source_ref']}")
        if knowledge.get("warnings"):
            lines.append("检索限制：" + "、".join(knowledge["warnings"]))
    lines.append("")

    summary = report.get("summary") or {}
    lines.append("## 1. 摘要")
    lines.append("")
    lines.append(
        f"共 {summary.get('total_issues', 0)} 条问题：blocker {summary.get('blocker', 0)}，"
        f"major {summary.get('major', 0)}，suggestion {summary.get('suggestion', 0)}。"
    )
    soft = (report.get("input_quality") or {}).get("soft_issues") or []
    if soft:
        lines.append("")
        lines.append("输入质量提示：" + "；".join(soft))
    lines.append("")

    issues = report.get("issues") or []
    sections = [
        ("2. 阻断问题", "blocker"),
        ("3. 重要问题", "major"),
        ("4. 建议项", "suggestion"),
    ]
    for title, severity in sections:
        subset = [issue for issue in issues if issue.get("severity") == severity]
        lines.append(f"## {title}")
        lines.append("")
        if not subset:
            lines.append("无。")
            lines.append("")
            continue
        for issue in subset:
            lines.append(f"### ISSUE-{issue.get('issue_no'):03d} · {issue.get('category')}")
            lines.append("")
            lines.append(f"- 位置：{_location(issue)}")
            lines.append(f"- 状态：`{issue.get('status')}` · 证据状态：`{issue.get('evidence_status')}`")
            lines.append(f"- 说明：{issue.get('rationale')}")
            if issue.get("suggestion"):
                lines.append(f"- 建议：{issue.get('suggestion')}")
            votes = issue.get("votes") or {}
            if votes:
                vote_text = "；".join(
                    f"{reviewer} {value.get('validity')}"
                    + (f"/{value.get('severity')}" if value.get("severity") else "")
                    for reviewer, value in votes.items()
                )
                lines.append(f"- 投票：{vote_text}")
            lines.append("")
            lines.append("判断链：")
            lines.append("")
            lines.append(f"1. 初始发现：{'、'.join(issue.get('proposed_by') or []) or '无'}")
            lines.append(f"2. 融合：候选 `{issue.get('candidate_id')}`")
            lines.append(f"3. 投票：{issue.get('vote_summary', {}).get('vote_completeness')}")
            lines.append(
                f"4. 证据：{issue.get('evidence_status')}"
                f"（kb_grounded={str(issue.get('kb_grounded')).lower()}）"
            )
            chief = issue.get("chief_decision") or "未触发仲裁"
            lines.append(f"5. 仲裁：{chief}")
            lines.append(f"6. 结论：状态 `{issue.get('status')}`，严重级 `{issue.get('severity')}`")
            human = "进入人工复核" if issue.get("status") in ("need_human", "disputed") else "未强制人工复核"
            lines.append(f"7. 人工：{human}")
            lines.append("")

    lines.append("## 5. 分歧与人工复核清单")
    lines.append("")
    items = report.get("human_review_items") or []
    if not items:
        lines.append("无。")
    else:
        for item in items:
            reason = REASON_LABELS.get(item.get("reason"), item.get("reason"))
            lines.append(f"- ISSUE-{item.get('issue_no'):03d}：{reason}（优先级 {item.get('priority', 'normal')}）")
    lines.append("")

    lines.append("## 6. 知识库缺口")
    lines.append("")
    gaps = report.get("kb_gaps") or []
    if not gaps:
        lines.append("本次未聚合到知识库缺口。")
    else:
        for gap in gaps:
            lines.append(
                f"- {gap.get('module')} / {gap.get('function_point')}："
                f"{gap.get('suspected_rule')}（{gap.get('status')}）"
            )
    lines.append("")

    lines.append("## 7. 附录")
    lines.append("")
    lines.append("### 7.1 原始意见摘要")
    appendix = report.get("appendix") or {}
    for role, opinion in (appendix.get("raw_opinions") or {}).items():
        lines.append(f"- {role}：{opinion.get('summary')}")
    lines.append("")
    lines.append("### 7.2 输入用例核对")
    normalized = appendix.get("normalized_case") or {}
    for step in normalized.get("steps") or []:
        lines.append(f"- 第 {step.get('index')} 步：{step.get('action')}")
    lines.append("")
    lines.append("### 7.3 模型调用")
    for run in appendix.get("model_runs") or []:
        lines.append(
            f"- {run.get('role')}：status={run.get('status')} latency_ms={run.get('latency_ms')}"
        )
    lines.append("")
    lines.append("### 7.4 附件")
    attachments = report.get("attachments") or []
    if not attachments:
        lines.append("本次评审未引用附件。")
    else:
        for attachment in attachments:
            lines.append(
                f"- {attachment.get('file_name')}（sha256 {str(attachment.get('sha256'))[:12]}…，"
                f"status={attachment.get('status')}）：附件仅存档，未发送给模型分析"
            )
    lines.append("")
    return "\n".join(lines)


def _location(issue: dict[str, Any]) -> str:
    step_index = issue.get("step_index")
    if step_index is None:
        return "用例整体"
    return f"第 {step_index} 步"
