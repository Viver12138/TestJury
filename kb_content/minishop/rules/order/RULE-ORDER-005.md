---
id: RULE-ORDER-005
title: 优惠券门槛与应付金额计算
knowledge_type: BUSINESS_RULE
project_id: minishop
module_id: order
source_type: OTHER
source_ref: Minishop/backend/app/api/orders.py#L76-L84
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
  - coupon
  - threshold
  - amount
related_ids:
  - RULE-ORDER-001
  - RULE-ORDER-004
  - REQ-ORDER-001
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 规则陈述

使用优惠券时，商品总金额必须大于等于券门槛；满足门槛后，优惠金额等于券面额，应付金额为 `max(商品总金额 - 优惠金额, 0)`。

# 2. 适用范围

- `POST /api/orders/preview`
- `POST /api/orders`
- 产品版本 `1.0.0`

# 3. 前置条件

- 已通过用券资格校验（见 `RULE-ORDER-004`）；
- 已计算商品总金额 `total_amount`。

# 4. 触发条件

请求携带通过资格校验的 `user_coupon_id`。

# 5. 规则结果

- 若 `total_amount < coupon.threshold`：409 `未达优惠券门槛（满<threshold>可用）`；
- 若 `total_amount >= coupon.threshold`：
  - `discount_amount = coupon.discount_amount`；
  - `pay_amount = round(max(total_amount - discount_amount, 0), 2)`。

# 6. 边界与例外

- 门槛比较使用**优惠前**的商品总金额，不是应付金额。
- 总金额恰好等于门槛时允许使用。
- 只支持一张券，不支持叠加、互斥组、券后价再打折。
- 券面额可能大于商品总金额（后台建券时未限制），此时应付金额为 0。
- 优惠金额不按比例分摊到订单明细，订单明细只保存原价与数量。
- 优惠券模板的 `threshold` 与 `discount_amount` 为 `float`，比较存在浮点精度风险。

# 7. 反例或禁止行为

- 禁止用“券后金额”判断是否达到门槛。
- 禁止多张券叠加。
- 禁止应付金额出现负数。
- 禁止在订单创建后重新计算优惠金额。

# 8. 验证方式

1. 总金额刚好等于门槛，确认可用且优惠正确。
2. 总金额比门槛少 0.01，确认返回 409。
3. 大额券使折扣大于总金额，确认 `pay_amount=0`。
4. 同一订单同时传两张券（接口只接受单个 `user_coupon_id`），确认为单券逻辑。
5. 核对预览与创建返回的 `discount_amount`、`pay_amount` 一致。

# 9. 来源依据

- `Minishop/backend/app/api/orders.py#L76-L84`：门槛比较、优惠金额与应付金额计算。
- `Minishop/backend/app/api/refunds.py#L28-L35`：退款金额使用订单 `pay_amount`，不重新算券。

# 10. 未决问题

- 券面额大于总金额时，是否应限制或按总金额封顶记录优惠？
- 是否需要把优惠金额分摊到明细，支持按商品退款？
- 金额是否应改为 Decimal？

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：门槛按优惠前总额判定、等额可用（< 比较）、409 消息含 {:g} 门槛、discount 取券面额、pay_amount=round(max(...),2)、不按比例分摊明细、后台建券不限制面额，均与 orders.py:77-84,150-158 与 coupons.py:98-110 一致；退款取 pay_amount 不重算券属实（refunds.py:31）。
- **复核备注**：无
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
