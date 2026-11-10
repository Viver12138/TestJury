# 19 · API 错误码与契约

> 版本：v1.6 · 2026-11-10（补充 15 落实：test_type 必填与兼容模式错误码）
> 目的：让调用方稳定识别"参数错、权限错、状态冲突、限流、模型失败、内部错误"，而不是靠 message 猜。
> 关联：03、18、20。

---

## 1. 统一响应结构

```json
{
  "error": {
    "code": "INPUT_INVALID",
    "message": "steps[2].expected 不能为空",
    "field": "steps[2].expected",
    "retryable": false,
    "request_id": "req-8f1c...",
    "details": {}
  }
}
```

- `code` 稳定、可枚举；`message` 面向人，可改；`field` 仅在字段级错误出现。
- `retryable` 告诉调用方是否值得重试。
- 不返回堆栈、供应商 Key、内部路径、SQL。

## 2. 错误码

| HTTP | code | 含义 | retryable |
|---|---|---|---|
| 400 | `INVALID_JSON` | 请求体不是合法 JSON | false |
| 400 | `INVALID_CASE` | 用例结构非法 | false |
| 401 | `UNAUTHORIZED` | API Key 缺失/错误 | false |
| 403 | `FORBIDDEN` | 角色不足（如 reviewer 审批） | false |
| 404 | `NOT_FOUND` | review/batch/decision 不存在 | false |
| 409 | `KB_MODULE_MISSING` | `strict_kb=true` 且模块未覆盖 | false |
| 409 | `DECISION_CONFLICT` | 并发审批冲突 | true（重新拉取后） |
| 409 | `INVALID_DECISION_STATE` | 终态后改判 | false |
| 409 | `REVIEW_IN_PROGRESS` | `force=true` 但旧代次仍在执行 | true（等待终态后） |
| 422 | `INPUT_INVALID` | API 同步硬校验失败，不创建任务 | false |
| 422 | `UNSUPPORTED_TEST_TYPE` | 测试类型不在 v1 支持范围（仅 `functional`），不创建任务 | false |
| 422 | `TEST_TYPE_REQUIRED` | 未提供测试类型且未启用兼容模式，不创建任务 | false |
| 422 | `IDEMPOTENCY_KEY_CONFLICT` | 同一幂等键对应不同请求体 | false |
| 422 | `TOO_MANY_CASES` | 批量超过上限 | false |
| 422 | `INVALID_DECISION` | 决定非法或缺少理由 | false |
| 429 | `QUEUE_FULL` | 队列已满 | true（按 Retry-After） |
| 429 | `BUDGET_EXCEEDED` | 批次/每日预算超限 | false |
| 502 | `OUTPUT_SCHEMA_INVALID` | 模型输出未过门禁且重试耗尽 | false |
| 503 | `ALL_MODELS_FAILED` | 三模型全部失败 | true（稍后重试） |
| 500 | `INTERNAL` | 未分类内部错误 | true（谨慎） |

> 硬校验必须在创建任务前完成；Worker 阶段失败不会返回 422，只会体现在任务状态与报告中。

## 3. 异步任务的"错误"表达

- 创建阶段：用 HTTP 4xx 表达硬错误。
- 执行阶段：用任务 `status=failed` + `error_code` + `degraded_reasons` 表达；查询接口返回：

```json
{
  "status": "failed",
  "error_code": "ARBITRATION_FAILED",
  "error_message": "仲裁重试耗尽",
  "partial_results_available": true
}
```

- `partial_results_available=true` 时，允许读取已完成阶段的输出，但不提供正式 `ai_verdict`。

## 4. 幂等与错误

> 行为矩阵以 `docs/03` §1.1 为唯一口径；本节只定义 HTTP 与错误码映射。

| 场景 | 行为 |
|---|---|
| 相同 `idempotency_key`，任务进行中 | **200** + 真实状态 + `idempotent_replay=true`（不返回 409） |
| 相同 key，任务失败 | **200** + `status=failed`；重跑需 `force=true` |
| 相同 key，任务完成 | **200** + 已有报告 + `idempotent_replay=true` |
| 相同 key，但请求体不同 | 422 `IDEMPOTENCY_KEY_CONFLICT`（同一 key 不得对应不同输入） |
| `force=true`，旧记录已终态 | **202** + 新 `review_id` + `generation+1`；旧记录 `superseded_by` 指向新记录；不返回 409 |
| `force=true`，旧记录仍在运行 | 409 `REVIEW_IN_PROGRESS`（状态冲突，不是幂等命中，也不是已废弃的 `DUPLICATE`） |
| 同一 key 两个并发请求 | 按 key 串行化；未 force 的后到者 200 返回已有记录；并发 force 由第一个新建代次，后到者因新代次在运行返回 409 `REVIEW_IN_PROGRESS`；**任何情况都不返回 409 `DUPLICATE`** |

> 幂等命中不是错误，未 force 统一 200；force 新建代次统一 202。409 只用于状态冲突：`REVIEW_IN_PROGRESS`、`DECISION_CONFLICT`、`INVALID_DECISION_STATE`、`KB_MODULE_MISSING`。`409 DUPLICATE` 已废弃，仓库内不得再出现。

## 5. 错误信息与安全

- 不回显用例正文、Prompt、模型原始输出。
- `details` 只放字段级修正提示，不放内部配置。
- 所有错误带 `request_id`，日志可关联。
- 供应商错误统一映射为本表，不把原始供应商报文透传给调用方。

## 6. 验收

- 每个错误码至少一个测试用例。
- 调用方能仅凭 `code` 决定重试/修正/放弃。
- 不存在"HTTP 200 但实际失败且无状态"的响应。
