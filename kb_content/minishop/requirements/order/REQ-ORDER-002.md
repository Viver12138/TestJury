---
id: REQ-ORDER-002
title: 模拟支付
knowledge_type: REQUIREMENT
project_id: minishop
module_id: order
source_type: REQUIREMENT_SPEC
source_ref: Minishop/README.md#L56-L57; Minishop/backend/app/api/payments.py#L15-L119
source_version: snapshot-2026-11-11
product_version:
  - "1.0.0"
platforms:
  - all
evidence_level: E2
status: approved
owner: minishop_project_team
reviewer: "平台设计者（产品负责人）"
created_at: 2026-11-11
updated_at: 2026-11-12
effective_from: null
effective_until: null
reviewed_at: 2026-11-11
review_cycle_days: 90
tags:
  - order
  - payment
  - state_transition
  - stock
related_ids:
  - RULE-ORDER-008
  - RULE-ORDER-009
  - STATE-ORDER-001
  - API-ORDER-005
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 需求背景与目标

MiniShop 不接入真实支付渠道，用“创建支付单 + 手动触发成功/失败”模拟支付，用于验证订单状态推进、金额来源、重复支付保护和库存扣减。

# 2. 用户与前置条件

- 用户已登录，且是目标订单的所有者；
- 订单存在且状态允许支付（实际可支付的状态为 `PENDING_PAYMENT`）；
- 订单金额由下单时服务端计算并固化在 `orders.pay_amount`。

# 3. 功能描述

## 3.1 创建支付单 `POST /api/payments`

- 入参：`order_id`、可选 `method`（默认 `WECHAT`，可传 `ALIPAY`）。
- 若该订单已有 `PENDING` 支付单，直接返回已有支付单（不重复创建）。
- 否则创建 `payment_no`、`amount=order.pay_amount`、`status=PENDING` 的支付记录。

## 3.2 支付成功 `POST /api/payments/{payment_id}/success`

- 校验支付单存在且订单归属当前用户；
- 拒绝已支付、已发货、已完成、售后中、已退款、已取消的订单；
- 支付金额强制改写为服务端订单应付金额；
- 支付单 `SUCCESS`，订单 `PAID` 并记录 `paid_at`；
- 扣减 SKU 与商品库存、增加销量、写库存日志、发送站内消息。

## 3.3 支付失败 `POST /api/payments/{payment_id}/fail`

- 仅允许订单仍为 `PENDING_PAYMENT`；
- 支付单置 `FAILED`，订单保持 `PENDING_PAYMENT`，用户可重新创建支付单重试。

# 4. 主成功场景

1. 用户对 `PENDING_PAYMENT` 订单创建支付单。
2. 前端调用 `success`。
3. 订单变为 `PAID`，支付金额等于订单 `pay_amount`。
4. 对应 SKU 库存减少购买数量，商品销量增加，生成库存日志。
5. 用户收到“订单支付成功”站内消息。
6. 管理员可对该订单发货（见 `REQ-ORDER-003`）。

# 5. 异常与替代场景

| 场景 | 预期结果 |
|---|---|
| 订单不存在或不属于当前用户 | 404 `订单不存在` |
| 订单已取消 | 409 `订单已取消，无法支付` |
| 订单已支付/已发货/已完成/售后中/已退款 | 409 `订单已支付，请勿重复支付` 或 `订单已进入售后流程` |
| 支付单不存在 | 404 `支付记录不存在` |
| 对已支付订单再次调用 `success` | 409 `订单已支付，请勿重复支付` |
| 对非待支付订单调用 `fail` | 409 `当前订单状态不支持支付失败操作` |
| 支付失败后再次支付 | 允许：新建支付单并调用 `success` |

# 6. 输入与输出

| 接口 | 入参 | 成功输出 |
|---|---|---|
| 创建支付 | `order_id`、`method` | 201，`data` 含 `id`、`payment_no`、`amount`、`status=PENDING` |
| 支付成功 | 无 | 200，`data` 含 `order_id`、`order_status=PAID` |
| 支付失败 | 无 | 200，`data` 含 `order_id`、`order_status=PENDING_PAYMENT` |

# 7. 业务约束

- 支付金额只能来自服务端订单 `pay_amount`，客户端不能指定金额。
- 支付成功是库存扣减的唯一触发点；下单阶段不扣库存。
- 库存扣减使用 `max(stock - quantity, 0)`，库存不足时不会报错，而是把库存截断为 0。
- 同一订单可以存在多条支付记录（失败后可再创建），但订单只有一个 `payment` 关系字段。
- 支付接口不校验 `payment.status`，理论上可对一条 `FAILED` 支付单再次调用 `success`（只要订单仍待支付）。
- `method` 没有枚举校验，任意字符串都会被接受；展示层只把 `WECHAT` 映射为“微信支付”，其余显示为“支付宝”。

# 8. 验收标准

1. 待支付订单可创建支付单，金额等于订单 `pay_amount`。
2. 重复创建支付单时，若已有 `PENDING` 支付单，返回同一条记录。
3. 支付成功后订单状态为 `PAID`，`paid_at` 非空。
4. 支付成功后 SKU 库存减少、商品销量增加、产生库存日志。
5. 重复支付返回 409，库存不重复扣减。
6. 支付失败后订单仍为 `PENDING_PAYMENT`，可再次支付。
7. 客户端传入的任何金额字段都不影响支付金额。
8. 非订单所有者不能创建或操作支付单。

# 9. 明确不支持的行为

- 真实第三方支付、支付回调、签名验签；
- 部分支付、组合支付、余额抵扣；
- 支付超时关闭、支付单撤销；
- 退款原路退回（退款为独立模拟流程）；
- 支付幂等键与并发安全保证。

# 10. 未决问题

- 支付失败后再支付成功，订单详情应展示哪条支付记录？当前 `Order.payment` 为单对象关系，多条记录时展示结果不确定。
- 是否需要对 `payment.status` 做状态机校验，禁止 `FAILED -> SUCCESS`？
- 是否需要金额二次校验（订单金额被篡改或历史数据异常时）？
- `PENDING_SHIPMENT` 状态未使用，支付成功后是否应进入该状态？

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：支付三接口门禁、金额强制取服务端 pay_amount、max(stock-qty,0) 截断、FAILED 后可再建支付、多支付记录与单对象关系的矛盾均与代码一致（payments.py:44-59,87-99；models.py:192）；已知缺陷写在未决问题，未包装成规则。
- **复核备注**：补记 Q-05 实测结论：SQLAlchemy 2.0.36 下 Order.payment 恒返回第一条（FAILED）并抛 SAWarning，属确定性缺陷。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
