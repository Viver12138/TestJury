---
id: RULE-ORDER-007
title: 只有待支付订单可以取消并归还优惠券
knowledge_type: BUSINESS_RULE
project_id: minishop
module_id: order
source_type: OTHER
source_ref: Minishop/backend/app/api/orders.py#L223-L244
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
  - cancel
  - coupon
  - state_transition
related_ids:
  - REQ-ORDER-004
  - RULE-ORDER-006
  - STATE-ORDER-001
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 规则陈述

只有订单所有者可以取消状态为 `PENDING_PAYMENT` 的订单；取消后订单进入 `CANCELLED` 终态，已占用的优惠券必须恢复为可用，券模板已使用数量回退 1。

# 2. 适用范围

- `POST /api/orders/{order_id}/cancel`
- 产品版本 `1.0.0`

# 3. 前置条件

- 用户已登录；
- 订单存在且 `user_id` 等于当前用户；
- 订单状态为 `PENDING_PAYMENT`。

# 4. 触发条件

用户对待支付订单提交取消请求。

# 5. 规则结果

- 订单 `status = CANCELLED`，`cancelled_at` 为当前时间；
- 若 `user_coupon_id` 非 0：
  - 用户券 `status = UNUSED`；
  - `used_order_id = 0`；
  - `used_at = None`；
  - 券模板 `used_quantity = max(used_quantity - 1, 0)`；
- 不修改库存、销量、支付记录；
- 订单不可恢复。

# 6. 边界与例外

- 非本人订单返回 **404**（不是 403），避免暴露订单存在性。
- 状态不是 `PENDING_PAYMENT` 时返回 409 `只有待支付订单可以取消`。
- 已创建但未支付的支付单不会被关闭，仍保留 `PENDING` 状态；后续调用支付成功会因订单已取消返回 409。
- 券归还后如果券已过期，查询“我的优惠券”时会动态显示为 `EXPIRED`，但数据库状态仍是 `UNUSED`。
- 若券模板已被删除或数据异常，代码对 `used_quantity` 的回退做了不小于 0 的保护。

# 7. 反例或禁止行为

- 禁止取消已支付及之后状态的订单。
- 禁止用户取消他人订单。
- 禁止在取消时恢复库存（下单未扣库存）。
- 禁止把取消当作退款使用。

# 8. 验证方式

1. 待支付订单取消，确认状态、`cancelled_at`。
2. 取消后查询用户券，确认 `UNUSED`、`used_order_id=0`。
3. 取消后再次下单使用同一张券，确认可用。
4. 已支付订单取消，确认 409。
5. 用户 B 取消用户 A 的订单，确认 404。
6. 取消前后查询 SKU 库存，确认不变。

# 9. 来源依据

- `Minishop/backend/app/api/orders.py#L223-L244`：取消逻辑、券归还、状态校验。
- `Minishop/backend/app/api/payments.py#L89-L90`：取消订单拒绝支付。

# 10. 未决问题

- 取消时是否应同步关闭 `PENDING` 支付单？
- 券归还后有效期是否顺延？
- 是否需要管理员代取消能力？
- 是否需要超时自动取消？

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：取消门禁、非本人返回 404 而非 403、券归还四动作（UNUSED/used_order_id=0/used_at=None/used_quantity 回退下限 0）、PENDING 支付单不关闭且再支付 409，均与 orders.py:226-242、payments.py:89-90 一致。
- **复核备注**：无
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
