# 03 · API 契约

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
  "options": {
    "force": false,
    "webhook_url": null
  }
}
```

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
  "versions": {
    "kb": "kb-2026-11-09-a3f9",
    "rubric": "rubric-7c21",
    "prompts": { "chief_blind": "p-1a2b", "arbitration": "p-3c4d", "jury_a": "p-5e6f", "jury_b": "p-7g8h" },
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
  "proposed_by": ["chief_blind", "jury_b"],
  "confidence": 0.85,
  "status": "adopted",
  "chief_decision": "adopt",
  "chief_reason": null,
  "human_verdict": null
}
```

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
7. 附录（三份原始意见摘要、输入用例核对、模型调用情况）

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
