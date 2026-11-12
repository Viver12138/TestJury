---
id: RULE-ORDER-003
title: 下单必须校验 SKU 有效、商品上架与 SKU 库存
knowledge_type: BUSINESS_RULE
project_id: minishop
module_id: order
source_type: OTHER
source_ref: Minishop/backend/app/api/orders.py#L45-L59
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
  - sku
  - stock
  - validation
related_ids:
  - REQ-ORDER-001
  - RULE-ORDER-001
  - RULE-ORDER-009
  - API-ORDER-001
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 规则陈述

预览或创建订单时，每个商品项必须依次满足：数量 ≥ 1、SKU 存在且为 `ACTIVE`、所属商品存在且为 `ON_SALE`、数量不超过该 SKU 的 `stock`；任一条件不满足则拒绝下单。

# 2. 适用范围

- `POST /api/orders/preview`
- `POST /api/orders`
- 产品版本 `1.0.0`

# 3. 前置条件

- 用户已登录；
- 请求包含至少一个商品项。

# 4. 触发条件

遍历请求中的每个 `items[]` 项。

# 5. 规则结果

校验顺序与结果：

| 顺序 | 条件 | 失败结果 |
|---:|---|---|
| 1 | `quantity >= 1` | 400 `购买数量不能小于 1` |
| 2 | SKU 存在且 `status=ACTIVE` | 400 `商品规格无效` |
| 3 | 商品存在且 `status=ON_SALE` | 400 `商品已下架` |
| 4 | `quantity <= sku.stock` | 409 `商品「<名称>」库存不足` |

通过后，单项小计按 `sku.price × quantity` 计入总金额。

# 6. 边界与例外

- 只校验 SKU 库存，不校验 `products.stock` 聚合库存。
- 不校验 SKU 与商品的一致性以外的关系（例如 SKU 是否属于请求期望的商品）。
- **不合并重复 SKU**：同一 `sku_id` 在 `items` 中出现多次时，每一项独立与 `sku.stock` 比较，合计数量可能超过库存。例如库存 2，提交两次 `quantity=2`，两项都会通过，订单合计 4。
- 库存为 0 时，任何 `quantity>=1` 都会被拒绝。
- 校验发生在创建订单前，但**不会扣减或锁定库存**；两个并发请求可以同时通过校验。

# 7. 反例或禁止行为

- 禁止对已下架商品下单。
- 禁止对失效 SKU 下单。
- 禁止把数量 0 或负数当作合法购买。
- 禁止把“校验通过”等同于“库存已占用”。

# 8. 验证方式

1. 数量 0、-1，预期 400。
2. 使用不存在或已停用的 SKU ID，预期 400。
3. 对已下架商品下单，预期 400。
4. 库存 1 的 SKU 购买 2，预期 409。
5. 同一 SKU 重复提交两次且合计超过库存，观察当前实现是否放行（用于确认该已知边界）。
6. 下单后查询 SKU 库存，确认未变化。

# 9. 来源依据

- `Minishop/backend/app/api/orders.py#L45-L59`：逐项校验与库存比较。
- `Minishop/backend/app/models/models.py#L73-L84`：SKU 的 `stock`、`status` 字段。
- `Minishop/backend/app/api/payments.py#L15-L36`：库存实际扣减点（支付成功时）。

# 10. 未决问题

- 是否应在校验前合并重复 SKU？
- 是否应校验 `products.stock` 与 SKU 库存之和一致？
- 是否应引入库存预占，避免并发超卖？

> 已确认（2026-11-11，Q-02）：不引入库存预占；超卖为 Demo 已知限制，支付时按 `max(stock-qty,0)` 截断，不再作为未决问题。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：四步校验顺序与错误消息逐条一致（orders.py:47-56）；重复 SKU 不合并致合计可超库存、只校验 sku.stock、下单不占用且并发可同时通过等边界与代码一致，并明确禁止把"校验通过"当作"已占用"。
- **复核备注**：补记 Q-02 决策：不引入库存预占，超卖定性为 Demo 已知限制。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
