---
id: API-ORDER-006
title: 管理员发货接口
knowledge_type: INTERFACE
project_id: minishop
module_id: order
source_type: API_SPEC
source_ref: Minishop/backend/app/api/admin.py#L156-L178; Minishop/backend/app/schemas/schemas.py#L177-L181
source_version: snapshot-2026-11-11
product_version:
  - "1.0.0"
platforms:
  - all
evidence_level: E2
status: approved
owner: minishop_project_team
reviewer: "平台设计者（技术负责人）"
created_at: 2026-11-11
updated_at: 2026-11-12
effective_from: null
effective_until: null
reviewed_at: 2026-11-11
review_cycle_days: 90
tags:
  - order
  - shipping
  - admin
  - api
related_ids:
  - REQ-ORDER-003
  - RULE-ORDER-010
  - RULE-ORDER-011
  - DATA-ORDER-001
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 接口用途

管理员对已支付订单录入物流公司与运单号，把订单推进为 `SHIPPED`，并通知用户。

# 2. 请求方式与路径

```http
POST /api/admin/orders/{order_id}/ship
Authorization: Bearer <ADMIN_JWT>
Content-Type: application/json
```

# 3. 身份认证与权限

- 必须登录且 `role=ADMIN`；普通用户返回 403 `需要管理员权限`。
- 无 token 返回 401。

# 4. 请求参数

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|:---:|---|---|
| `order_id` | path int | 是 | 订单存在 | 目标订单 |
| `company` | string | 是 | 无长度/非空校验 | 物流公司 |
| `tracking_number` | string | 是 | 无长度/格式/非空校验 | 运单号 |

```json
{"company": "顺丰", "tracking_number": "SF123456789"}
```

# 5. 响应字段

HTTP 200：

```json
{
  "code": "OK",
  "message": "发货成功",
  "data": {"order_id": 1, "status": "SHIPPED"}
}
```

# 6. 错误码与异常

| HTTP | `message` | 触发条件 |
|---:|---|---|
| 403 | `需要管理员权限` | 非管理员 |
| 404 | `订单不存在` | 订单 ID 不存在 |
| 409 | `只有已支付/待发货的订单可以发货` | 状态不在 `PAID`/`PENDING_SHIPMENT` |
| 400 | `VALIDATION_ERROR` | `company` 或 `tracking_number` 缺失/类型错误 |

# 7. 幂等、重试与并发约束

- 不支持重复发货：订单已 `SHIPPED` 后再次调用返回 409。
- 若已存在物流单，会更新而不是新增。
- 无运单号唯一性校验。
- `PENDING_SHIPMENT` 在实际代码中从未赋值，因此实际入口只有 `PAID`。

# 8. 测试数据准备

1. 创建订单并支付成功，使订单为 `PAID`；
2. 准备管理员 token；
3. 记录用户 `messages` 数量，便于验证发货消息。

# 9. 结果查询与验证

1. 断言 HTTP 200、`status=SHIPPED`；
2. 查询订单详情，断言 `status=SHIPPED`、`shipped_at` 非空、`shipment` 存在且字段与入参一致；
3. 查询用户消息，断言新增“订单已发货”；
4. 重复发货，断言 409；
5. 普通用户调用，断言 403；
6. 传空字符串物流信息，确认当前是否接受（已知边界）。

# 10. 来源与未决问题

## 来源

- `Minishop/backend/app/api/admin.py#L156-L178`：发货实现、物流单 upsert、消息。
- `Minishop/backend/app/schemas/schemas.py#L177-L181`：请求模型。

## 未决问题

- 已确认（2026-11-11，Q-11）：后端应拒绝空物流公司/空运单号；当前未校验，属缺陷待修复。前端 `AdminOrders.tsx#L38、L107-L108` 已有必填校验，API 用例应期望 400/422。
- 是否需要物流公司枚举、运单号格式校验？
- 是否需要部分发货、多包裹、发货撤销？
- 是否需要记录发货操作日志（`operation_logs` 表未使用）？

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：路径/403/404/409 文案、物流单存在则更新不新增、发货发消息、company 与 tracking_number 无非空校验（schemas.py:178-180）、PENDING_SHIPMENT 从未赋值故实际入口仅 PAID，均核实一致。
- **复核备注**：按 Q-11 决策把"是否应拒绝空物流信息"从未决问题升级为"已确认缺陷待修复（后端）"，并注明前端 AdminOrders.tsx:38 已有必填校验。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
