---
id: API-ORDER-004
title: 取消订单与确认收货接口
knowledge_type: INTERFACE
project_id: minishop
module_id: order
source_type: API_SPEC
source_ref: Minishop/backend/app/api/orders.py#L223-L260
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
  - cancel
  - confirm
  - api
related_ids:
  - REQ-ORDER-003
  - REQ-ORDER-004
  - RULE-ORDER-007
  - RULE-ORDER-010
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 接口用途

- 取消：把待支付订单置为 `CANCELLED` 并归还优惠券。
- 确认收货：把已发货订单置为 `COMPLETED` 并把物流单置为 `DELIVERED`。

# 2. 请求方式与路径

```http
POST /api/orders/{order_id}/cancel
POST /api/orders/{order_id}/confirm
Authorization: Bearer <JWT>
```

无请求体。

# 3. 身份认证与权限

- 必须是订单所有者；非本人返回 **404**（不暴露存在性）。
- 无 token 返回 401。
- 管理员不能通过这两个接口操作他人订单（仍按所有者校验）。

# 4. 请求参数

| 字段 | 类型 | 必填 | 说明 |
|---|---|:---:|---|
| `order_id` | path int | 是 | 订单 ID |

# 5. 响应字段

## 取消成功（HTTP 200）

```json
{"code": "OK", "message": "订单已取消", "data": null}
```

## 确认收货成功（HTTP 200）

```json
{"code": "OK", "message": "确认收货成功", "data": null}
```

# 6. 错误码与异常

## 取消

| HTTP | `message` | 触发条件 |
|---:|---|---|
| 404 | `订单不存在` | 订单不存在或非本人 |
| 409 | `只有待支付订单可以取消` | 状态非 `PENDING_PAYMENT` |

## 确认收货

| HTTP | `message` | 触发条件 |
|---:|---|---|
| 404 | `订单不存在` | 订单不存在或非本人 |
| 409 | `只有已发货订单可以确认收货` | 状态非 `SHIPPED` |

# 7. 幂等、重试与并发约束

- 两个接口都**不是幂等**的语义：重复调用返回 409，不会重复执行成功。
- 取消是终态，不可恢复。
- 确认收货是终态，不可恢复。
- 并发重复调用时，后到请求通常看到已变更状态并返回 409；无显式行锁。

# 8. 测试数据准备

- 取消：创建一笔 `PENDING_PAYMENT` 订单；若使用优惠券，记录用户券 ID。
- 确认收货：创建订单 → 支付成功 → 管理员发货，使状态为 `SHIPPED`。

# 9. 结果查询与验证

## 取消

1. 断言 200、消息 `订单已取消`；
2. 查询订单，断言 `CANCELLED`、`cancelled_at` 非空；
3. 若用券，断言用户券 `UNUSED`、`used_order_id=0`；
4. 再次取消，断言 409；
5. 尝试支付，断言 409。

## 确认收货

1. 断言 200、消息 `确认收货成功`；
2. 查询订单，断言 `COMPLETED`、`completed_at` 非空；
3. 查询物流，断言 `DELIVERED`；
4. 再次确认，断言 409。

# 10. 来源与未决问题

## 来源

- `Minishop/backend/app/api/orders.py#L223-L244`：取消、优惠券归还。
- `Minishop/backend/app/api/orders.py#L247-L260`：确认收货、物流状态。

## 未决问题

- 取消时已创建的 `PENDING` 支付单是否应关闭？
- 是否需要取消原因？
- 确认收货后是否需要通知、结算或自动评价入口？

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：取消/确认路径与 200 文案、非本人（含管理员）一律 404、409 条件、券恢复三动作、物流置 DELIVERED 与 orders.py:226-258 完全一致。
- **复核备注**：无
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
