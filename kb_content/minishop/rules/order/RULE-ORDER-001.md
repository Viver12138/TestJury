---
id: RULE-ORDER-001
title: 订单金额必须由服务端重算
knowledge_type: BUSINESS_RULE
project_id: minishop
module_id: order
source_type: OTHER
source_ref: Minishop/backend/app/api/orders.py#L46-L59; Minishop/backend/app/api/orders.py#L83-L84;
  Minishop/backend/app/api/orders.py#L124-L130
source_version: snapshot-2026-11-11
product_version:
- 1.0.0
platforms:
- all
evidence_level: E2
status: approved
owner: minishop_project_team
reviewer: codex-delegated-reviewer
created_at: 2026-11-11
updated_at: '2026-11-12'
effective_from: null
effective_until: null
reviewed_at: '2026-11-12'
review_cycle_days: 90
tags:
- order
- amount
- pricing
- server_authoritative
related_ids:
- REQ-ORDER-001
- RULE-ORDER-005
- API-ORDER-001
- API-ORDER-002
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: delegated_review_completed
change_reason: 2026-11-12 用户授权技术复核；具体依据见 evidence/M2/delegated_content_review.json
---

# 1. 规则陈述

订单预览与创建时，商品总金额、优惠金额、应付金额均由服务端重新计算，客户端提交的任何价格或金额字段都不参与计算。

# 2. 适用范围

- `POST /api/orders/preview`
- `POST /api/orders`
- 产品版本 `1.0.0`

# 3. 前置条件

- 请求已通过登录鉴权；
- 请求包含至少一个商品项。

# 4. 触发条件

调用订单预览或创建订单接口。

# 5. 规则结果

- 单项小计 = `product_skus.price × quantity`；
- 商品总金额 `total_amount` = 所有单项小计之和；
- 优惠金额 `discount_amount` = 所用优惠券的 `discount_amount`，未用券时为 0；
- 应付金额 `pay_amount` = `round(max(total_amount - discount_amount, 0), 2)`；
- 订单落库的 `total_amount`、`discount_amount`、`pay_amount` 使用上述服务端结果。

# 6. 边界与例外

- 多个商品项时逐项累加，不按商品去重。
- 使用 `product_skus.price`，不是 `products.price`；两者在多规格商品上可能不同。
- 折扣大于商品总金额时，应付金额截断为 0，不会为负数。
- 金额使用浮点数计算：预览返回的 `total_amount`/`discount_amount` 未舍入；创建订单落库时三金额与 `OrderItem.subtotal` 均 round 到 2 位（orders.py#L128-L130、#L158）。
- 请求体中的未知字段（如 `price`、`pay_amount`）被 Pydantic 默认忽略，不产生作用。

# 7. 反例或禁止行为

- 禁止信任客户端传入的商品单价、总价、优惠金额或应付金额。
- 禁止用 `products.price` 覆盖 SKU 成交价。
- 禁止在预览与创建两个接口使用不同的计价逻辑。

# 8. 验证方式

1. 正常下单，核对响应与订单详情的三个金额。
2. 在请求体中额外传 `price: 0.01`、`pay_amount: 0.01`，确认订单金额不变。
3. 对多规格商品选择一个 `price` 与商品主价格不同的 SKU，确认按 SKU 价格计算。
4. 使用大额券使折扣大于总金额，确认 `pay_amount=0`。

# 9. 来源依据

- `Minishop/backend/app/api/orders.py#L46-L59`：逐项读取 SKU 价格并累加。
- `Minishop/backend/app/api/orders.py#L83-L84`：折扣与应付金额计算。
- `Minishop/backend/app/api/orders.py#L124-L130`：订单落库金额。

# 10. 未决问题

- 是否需要引入 Decimal 或分为单位，避免浮点误差？
- 单项小计是否需要单独四舍五入后再汇总？
- 是否应拒绝包含未知价格字段的请求，而不是静默忽略？


# 本次授权技术复核适用性

核对订单计价与落库：预览 total_amount 未 round，pay_amount 已 round，订单与明细落库分别 round；SKU 价格为来源。

本次结论基于冻结快照与既有决策，当前实现中的限制不代表目标规格；已决策但未实施的项目仍按治理台账单独跟踪。复核者为用户授权的 AI 代理，非新增人工签署。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：修改后通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：§6 称"只对订单总金额做 2 位四舍五入、单项小计未单独舍入"不准确：pay_amount 计算时即 round（orders.py:84），落库时订单三金额均 round（orders.py:128-130），OrderItem.subtotal 落库亦 round（orders.py:158），且与其 §5 自相矛盾。其余（按 sku.price 计价、max 截断为 0、未知字段忽略）一致。
- **复核备注**：修订要求：改为"预览返回的 total_amount/discount_amount 未舍入；落库时订单三金额与单项小计均四舍五入到 2 位"。
- **回写说明**：2026-11-12 已按复核意见回写；仍为 in_review，待复审后置 approved。
