---
id: API-ORDER-005
title: 支付创建、成功与失败接口
knowledge_type: INTERFACE
project_id: minishop
module_id: order
source_type: API_SPEC
source_ref: Minishop/backend/app/api/payments.py#L39-L118; Minishop/backend/app/schemas/schemas.py#L152-L156
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
  - payment
  - api
related_ids:
  - REQ-ORDER-002
  - RULE-ORDER-008
  - RULE-ORDER-009
  - DATA-ORDER-001
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 接口用途

以“创建支付单 → 标记成功/失败”的方式模拟支付，驱动订单从 `PENDING_PAYMENT` 到 `PAID`，并在成功时扣减库存。

# 2. 请求方式与路径

```http
POST /api/payments                     # 创建支付单（201）
POST /api/payments/{payment_id}/success # 支付成功（200）
POST /api/payments/{payment_id}/fail    # 支付失败（200）
Authorization: Bearer <JWT>
```

# 3. 身份认证与权限

- 必须登录；
- 支付单所属订单必须属于当前用户，否则 404 `订单不存在`；
- 无管理员专用支付接口。

# 4. 请求参数

## 创建支付单

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|:---:|---|---|
| `order_id` | int | 是 | 订单属于当前用户 | 目标订单 |
| `method` | string | 否 | 默认 `WECHAT`，无枚举校验 | 支付方式 |

```json
{"order_id": 1, "method": "WECHAT"}
```

## 成功/失败

无请求体，仅路径参数 `payment_id`。

# 5. 响应字段

## 创建支付单（HTTP 201）

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "id": 1,
    "order_id": 1,
    "payment_no": "PAY202611111731001234",
    "amount": 1187.0,
    "method": "WECHAT",
    "status": "PENDING"
  }
}
```

## 支付成功（HTTP 200）

```json
{"code": "OK", "message": "支付成功", "data": {"order_id": 1, "order_status": "PAID"}}
```

## 支付失败（HTTP 200）

```json
{"code": "OK", "message": "支付失败", "data": {"order_id": 1, "order_status": "PENDING_PAYMENT"}}
```

# 6. 错误码与异常

## 创建支付单

| HTTP | `message` | 触发条件 |
|---:|---|---|
| 404 | `订单不存在` | 订单不存在或非本人 |
| 409 | `订单已取消，无法支付` | 订单 `CANCELLED` |
| 409 | `订单已支付，请勿重复支付` | 订单 `PAID/PENDING_SHIPMENT/SHIPPED/COMPLETED` |
| 409 | `订单已进入售后流程` | 订单 `REFUNDING/REFUNDED` |

## 支付成功

| HTTP | `message` | 触发条件 |
|---:|---|---|
| 404 | `支付记录不存在` | `payment_id` 不存在 |
| 404 | `订单不存在` | 支付单对应订单不存在或非本人 |
| 409 | `订单已支付，请勿重复支付` | 订单已是支付后状态 |
| 409 | `订单已取消，无法支付` | 订单 `CANCELLED` |

## 支付失败

| HTTP | `message` | 触发条件 |
|---:|---|---|
| 404 | `支付记录不存在` / `订单不存在` | 支付单或订单不存在/非本人 |
| 409 | `当前订单状态不支持支付失败操作` | 订单非 `PENDING_PAYMENT` |

# 7. 幂等、重试与并发约束

- 创建支付单：若已存在 `PENDING` 支付单，返回同一记录（不新建）；`FAILED` 记录不阻止新建。
- 支付成功：依赖订单状态防重；不校验支付单状态；并发下无行锁。
- 支付失败：可重复调用（订单仍待支付），每次把支付单置 `FAILED`。
- 同一订单可存在多条支付记录（失败重试）；订单的 `payment` 关系只暴露一条。

# 8. 测试数据准备

1. 创建一笔 `PENDING_PAYMENT` 订单（见 `API-ORDER-002`）；
2. 记录订单 `pay_amount`；
3. 记录 SKU 支付前库存和商品销量；
4. 创建支付单，记录 `payment_id`。

# 9. 结果查询与验证

1. 创建支付单：断言金额等于订单 `pay_amount`，状态 `PENDING`；
2. 再次创建：断言返回同一 `payment_id`；
3. 支付成功：断言订单 `PAID`、支付单 `SUCCESS`、库存与销量变化、库存日志新增、消息新增；
4. 再次成功：断言 409，库存不重复扣减；
5. 支付失败：断言支付单 `FAILED`、订单仍 `PENDING_PAYMENT`；再次创建支付单应得到新记录。

# 10. 来源与未决问题

## 来源

- `Minishop/backend/app/api/payments.py#L39-L74`：创建支付单。
- `Minishop/backend/app/api/payments.py#L77-L103`：支付成功。
- `Minishop/backend/app/api/payments.py#L106-L118`：支付失败。
- `Minishop/backend/app/schemas/schemas.py#L152-L156`：请求模型。

## 未决问题

- 是否校验 `payment.status`，禁止 `FAILED → SUCCESS`？
- 多支付记录时订单详情如何选择？
- 是否需要支付幂等键、金额签名、回调验签？
- `method` 是否应限制枚举？

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：三接口状态码与全部错误文案逐条核实（payments.py:39-119）；金额取服务端 pay_amount、已支付 409 拒重复支付、PENDING 单复用而 FAILED 不阻止新建、不校验支付单状态均一致。
- **复核备注**：补记 Q-05 决策与实测结论。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
