# 03 · API 契约

> 版本：v0.2（并入评审修订：`test_scope` / `automation_context` / 投票计数 / 证据溯源）

- Base：`/v1`
- 鉴权：请求头 `X-API-Key: <key>`，调用方标识 `X-Caller-Id: <团队/系统名>`
- 内容类型：`application/json; charset=utf-8`
- 时间：ISO 8601（`2026-11-09T10:00:00+08:00`）
- 错误统一结构：

```json
{ "error": { "code": "INVALID_CASE", "message": "steps[2].expected 不能为空", "field": "steps[2].expected" } }
```

## 1. 提交单份评审

`POST /v1/reviews`

### 请求体

```json
{
  "case": {
    "case_id": "TC-DIG-0012",
    "module": "挖宝",
    "title": "洛阳挖宝 - 藏宝点发现与挖掘",
    "priority": "P1",
    "source": "manual",
    "preconditions": ["角色等级 ≥ 20", "背包至少 1 个空格"],
    "steps": [
      { "index": 1, "action": "点击【开始挖宝】按钮", "expected": "界面提示“已生成藏宝点”，地图出现藏宝点标记" },
      { "index": 2, "action": "传送到洛阳藏宝点坐标 (312, 480)", "expected": "角色到达藏宝点范围" },
      { "index": 3, "action": "点击【发现】按钮", "expected": "获得随机物品并进入背包" }
    ],
    "test_data": { "map": "洛阳", "item_pool": "普通藏宝池" },
    "raw_text": null,
    "kb_hint": null
  },
  "test_scope": {
    "feature_point": "藏宝点发现",
    "required_scenarios": ["正常发现", "背包已满", "重复点击", "跨地图挖宝"],
    "related_case_ids": ["TC-DIG-0008", "TC-DIG-0015"],
    "scope_version": "scope-2026-11-01"
  },
  "automation_context": {
    "framework": "自研 UI 自动化框架",
    "supported_operations": ["点击", "输入", "读取背包接口"],
    "state_query_capabilities": ["背包物品列表", "角色坐标"],
    "data_setup_capabilities": ["GM 指令发放道具"],
    "limitations": ["无自动寻路", "无法读取战斗日志"]
  },
  "options": {
    "force": false,
    "webhook_url": null
  }
}
```

`test_scope` 与 `automation_context` 均可省略，但省略会限制评审能下的结论（见下方字段规则与 `docs/04` §7）。

### 字段规则

| 字段 | 必填 | 说明 |
|---|---|---|
| `case.case_id` | 是 | 全局唯一用例标识；同一 ID 多次提交按幂等键判定 |
| `case.module` | 是 | 用于知识库检索；未命中则降级评审 |
| `case.title` | 是 | 用例标题 |
| `case.preconditions` | 否 | 数组，缺失时由评审提示 |
| `case.steps` | 条件必填 | 数组；若为 `null`/空，必须提供 `raw_text` |
| `case.steps[].index` | 是 | 从 1 开始的连续整数 |
| `case.steps[].action` | 是 | 操作描述，非空 |
| `case.steps[].expected` | 否 | 允许缺失 —— 缺失本身就是评审要抓的问题 |
| `case.raw_text` | 条件必填 | 纯文本用例；服务端预处理结构化，失败则降级 |
| `case.priority` | 否 | P0/P1/P2/P3 |
| `case.source` | 否 | `manual` / `auto`，默认 `manual` |
| `test_scope.feature_point` | 否 | 当前评审所属功能点；缺失时不得输出"功能点整体覆盖"结论 |
| `test_scope.required_scenarios` | 否 | 该功能点要求覆盖的场景清单（字符串数组） |
| `test_scope.related_case_ids` | 否 | 同一功能点下的关联用例 ID，用于判断用例间覆盖关系 |
| `test_scope.scope_version` | 否 | 测试范围定义版本；变更即视为新的评审上下文 |
| `automation_context.framework` | 否 | 自动化测试框架名称/版本 |
| `automation_context.supported_operations` | 否 | 框架支持的操作能力 |
| `automation_context.state_query_capabilities` | 否 | 能否程序化读取断言所需状态 |
| `automation_context.data_setup_capabilities` | 否 | 能否程序化准备/清理测试数据 |
| `automation_context.limitations` | 否 | 已知框架限制；缺失时"不可自动化"结论降级为待确认 |
| `options.force` | 否 | 跳过幂等检查，强制重评，默认 `false` |
| `options.webhook_url` | 否 | 完成后回调（POST 报告摘要） |

### 响应

```json
// 202 Accepted
{
  "review_id": "8f1c...",
  "status": "queued",
  "poll_url": "/v1/reviews/8f1c..."
}
```

若命中幂等键且未 `force`，返回 **200** + 已有报告（`status=done`）。

---

## 2. 查询评审结果

`GET /v1/reviews/{review_id}`

```json
{
  "review_id": "8f1c...",
  "case_id": "TC-DIG-0012",
  "module": "挖宝",
  "status": "done",
  "stage": "done",
  "verdict": "blocked",
  "degraded": false,
  "degraded_reasons": [],
  "participants": ["chief:qwen-max", "jury_a:deepseek-flash", "jury_b:kimi-k3"],
  "retrieval": {
    "mode": "hybrid",
    "channels": ["filter", "fts", "vector", "rrf", "rerank"],
    "evidence_count": 9,
    "degraded_reasons": []
  },
  "versions": {
    "kb": "kb-2026-11-09-a3f9",
    "rubric": "rubric-7c21",
    "prompts": { "chief_blind": "p-1a2b", "arbitration": "p-3c4d", "jury_a": "p-5e6f", "jury_b": "p-7g8h", "vote": "p-8i9j" },
    "retrieval_config": "rc-9f2e",
    "embedding_profile": "qwen3.7-text-embedding-flash@v1/1024/cosine",
    "models": { "qwen-max": "qwen-max-2026-10", "deepseek-flash": "deepseek-chat-v3", "kimi-k3": "kimi-k3-2026-08" }
  },
  "summary": {
    "total_issues": 6,
    "blocker": 2, "major": 3, "suggestion": 1,
    "kb_grounded": 4,
    "inferred": 2,
    "disputed": 1,
    "human_review_required": 2
  },
  "issues": [ /* 见 §2.1 */ ],
  "human_review_list": [ { "issue_no": 2, "reason": "主审驳回陪审提出的阻断问题" } ],
  "kb_gaps": [ /* 见 §2.2 */ ],
  "scope": {
    "feature_point": "藏宝点发现",
    "scope_version": "scope-2026-11-01",
    "provided": true,
    "coverage_claims_allowed": true
  },
  "appendix": {
    "raw_opinions": {
      "chief_blind": { "summary": "...", "issues": [ /* 原始 */ ] },
      "jury_a":      { "summary": "...", "issues": [ /* 原始 */ ] },
      "jury_b":      { "summary": "...", "issues": [ /* 原始 */ ] }
    },
    "disagreements": [ { "step_index": 3, "dimension": "business", "claims": [ /* 双方理由 */ ] } ],
    "model_runs": [ { "role": "chief_blind", "model": "qwen-max", "status": "ok", "latency_ms": 18400, "tokens": 31200 } ],
    "normalized_case": { /* 预处理后的用例，供核对 */ }
  },
  "created_at": "2026-11-09T10:00:00+08:00",
  "finished_at": "2026-11-09T10:01:25+08:00"
}
```

`degraded_reasons` 取值：`kb_module_missing`、`raw_text_unparsed`、`vector_unavailable`、`fts_unavailable`、`rerank_skipped`、`model_missing`、`scope_missing`、`automation_context_missing`。前六项是链路降级，后两项限制结论强度，都必须在报告顶部明示。

### 2.1 issue 结构

```json
{
  "issue_no": 1,
  "step_index": 3,
  "dimension": "test_design",
  "severity": "blocker",
  "category": "预期不明确",
  "evidence_quote": "点击【发现】按钮 → 获得随机物品并进入背包",
  "rationale": "未说明随机池范围与判定条件，执行者无法判断结果是否正确。",
  "suggestion": "补充物品池范围，并明确至少验证“背包物品数量 +1”与“物品来源为藏宝池”。",
  "kb_grounded": true,
  "kb_refs": ["RULE-DIG-012"],
  "evidence_refs": [
    {
      "ref": "chunk:8842",
      "source_ref": "挖宝/requirements.md#3.2 藏宝点",
      "heading_path": "3 挖宝流程 > 3.2 藏宝点",
      "doc_type": "requirement",
      "retrieval_channel": "fts+vector",
      "rerank_score": 0.91
    }
  ],
  "proposed_by": ["chief_blind", "jury_b"],
  "votes": {
    "chief_blind": "accept",
    "jury_a": "not_assessed",
    "jury_b": "accept"
  },
  "vote_summary": {
    "support": 2, "reject": 0, "not_assessed": 1, "uncertain": 0,
    "support_ratio": 0.67
  },
  "confidence": null,
  "confidence_source": "uncalibrated",
  "status": "adopted",
  "chief_decision": "adopt",
  "chief_reason": null,
  "human_verdict": null
}
```

字段约定：

- `votes` 必须覆盖每个参与模型；未表态一律记 `not_assessed`，不得省略。
- `not_assessed` 不计入 `reject`，服务端按 `docs/01` §7 重新计算结论。
- `confidence` 未校准时为 `null`，报告展示 `support_ratio` 与计数；校准后才写数值并标 `confidence_source=calibrated`。
- `evidence_refs` 至少一条对应 `kb_grounded=true` 的知识条目；无 KB 依据时为空数组。

### 2.2 kb_gap 结构

```json
{
  "module": "挖宝",
  "function_point": "藏宝点发现",
  "suspected_rule": "藏宝点是否存在冷却时间",
  "occurrences": 3,
  "examples": ["第 2 步未说明连续挖宝的冷却限制"],
  "status": "open"
}
```

---

## 3. Markdown 报告

`GET /v1/reviews/{review_id}/report`，`Accept: text/markdown`

章节固定为：

1. 摘要
2. 阻断问题
3. 重要问题
4. 建议项
5. 分歧与人工复核清单
6. 知识库缺口
7. 附录（三份原始意见摘要、投票明细、证据清单与原文位置、输入用例核对、模型调用情况）

---

## 4. 批量评审

`POST /v1/review-batches`

```json
{
  "cases": [ /* case 对象数组，≤ 50 */ ],
  "options": { "force": false, "webhook_url": null }
}
```

响应 202：

```json
{ "batch_id": "b-2e9f...", "total": 37, "poll_url": "/v1/review-batches/b-2e9f..." }
```

`GET /v1/review-batches/{batch_id}`

```json
{
  "batch_id": "b-2e9f...",
  "status": "processing",
  "total": 37, "done": 21, "failed": 1, "queued": 15,
  "items": [ { "case_id": "TC-DIG-0012", "review_id": "8f1c...", "status": "done", "verdict": "blocked" } ],
  "overview": {
    "verdict_distribution": { "blocked": 8, "conditional": 12, "need_human": 1 },
    "hot_modules": [ { "module": "挖宝", "blocker": 5 }, { "module": "背包仓库", "blocker": 3 } ]
  }
}
```

批次完成后再提供 `GET /v1/review-batches/{batch_id}/report`（总览 Markdown）。

---

## 5. 复核回写

`POST /v1/reviews/{review_id}/feedback`

```json
{
  "reviewer": "zhangsan",
  "final_verdict": "approved",
  "issues": [
    { "issue_no": 1, "verdict": "adopted", "note": "确认是问题" },
    { "issue_no": 2, "verdict": "rejected", "note": "主审驳回正确" },
    { "verdict": "missed", "note": "漏检：未检查背包满时的失败提示", "step_index": 3,
      "severity": "major", "dimension": "test_design" }
  ]
}
```

- `final_verdict=approved` 是系统结论变“通过”的唯一途径。
- `missed` 记录用于计算召回率（漏检），必须带 `step_index` 与 `severity`。

---

## 6. 知识库与缺口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/v1/kb/modules` | 当前知识库覆盖的模块与功能点树 |
| GET | `/v1/kb/rules?module=挖宝` | 某模块的全部规则（含 RULE-ID 与出处） |
| POST | `/v1/kb/search` | 调试检索：入参 `{query, module, function_point, doc_type, top_k}`，返回各通道排名、RRF 分数、rerank 分数与溯源字段；供检索评测与调参使用 |
| GET | `/v1/kb/gaps?status=open` | 缺口清单，按 occurrences 降序 |
| PATCH | `/v1/kb/gaps/{id}` | 更新缺口状态：`accepted` / `dismissed` / `merged` |

---

## 7. 其他

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/v1/reviews?case_id=&module=&verdict=&from=&to=&page=` | 报告列表与筛选 |
| GET | `/healthz` | 健康检查，含队列深度与 DB 连通性 |

## 8. 错误码

| HTTP | code | 含义 |
|---|---|---|
| 400 | `INVALID_CASE` | 用例结构非法（给出具体字段） |
| 401 | `UNAUTHORIZED` | API Key 缺失或错误 |
| 404 | `NOT_FOUND` | review_id / batch_id 不存在 |
| 409 | `KB_MODULE_MISSING` | 模块未覆盖（**仅在 options.strict_kb=true 时返回**；默认降级不报错） |
| 409 | `DUPLICATE` | 命中幂等键且未 force（此时正常返回已有结果，见 §1） |
| 422 | `TOO_MANY_CASES` | 批量超过 50 份 |
| 429 | `QUEUE_FULL` | 队列已满，返回 `Retry-After` |
| 500 | `INTERNAL` | 服务内部错误 |
| 503 | `ALL_MODELS_FAILED` | 三模型全部失败 |
