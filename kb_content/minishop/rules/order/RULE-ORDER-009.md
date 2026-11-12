---
id: RULE-ORDER-009
title: 支付成功时扣减库存、增加销量并写库存日志
knowledge_type: BUSINESS_RULE
project_id: minishop
module_id: order
source_type: OTHER
source_ref: Minishop/backend/app/api/payments.py#L15-L36; Minishop/backend/app/api/payments.py#L92-L102
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
  - stock
  - sales
  - inventory_log
related_ids:
  - RULE-ORDER-008
  - RULE-ORDER-003
  - REQ-ORDER-002
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 规则陈述

订单支付成功时，系统按订单明细逐项扣减 SKU 库存和商品库存、增加商品销量，并为每一项写入一条库存日志；库存不足时不会中断支付，而是把库存截断为 0。

# 2. 适用范围

- `POST /api/payments/{payment_id}/success`
- 产品版本 `1.0.0`

# 3. 前置条件

- 支付单与订单存在，且订单属于当前用户；
- 订单状态通过支付成功门禁（见 `RULE-ORDER-008`）。

# 4. 触发条件

支付单被标记为 `SUCCESS`，订单状态置为 `PAID`。

# 5. 规则结果

对订单的每个 `order_items`：

1. 读取 SKU 当前库存 `before`；
2. `sku.stock = max(before - quantity, 0)`；
3. 若商品存在：`product.stock = max(product.stock - quantity, 0)`；
4. `product.sales = (product.sales or 0) + quantity`；
5. 写入 `inventory_logs`：
   - `change_quantity = -quantity`
   - `before_quantity = before`
   - `after_quantity = sku.stock`
   - `reason = 订单支付扣减库存`
   - `operator_id = 当前用户 ID`
6. 给用户写入“订单支付成功”站内消息。

# 6. 边界与例外

- **不检查库存是否充足**：因为下单只校验不占用，支付时可能已被其他订单扣走；此时仍支付成功，库存被截断为 0。
- **同一订单内重复 SKU**：每个明细独立扣减，可能重复扣减同一 SKU。
- **商品聚合库存**：`products.stock` 与 SKU 库存之和可能因截断而不一致；多规格商品的聚合库存不是强一致字段。
- **销量**：支付成功即增加销量；后续退款成功会回减销量（见售后模块，本批未覆盖）。
- **日志操作者**：记录的是下单用户，不是管理员。
- 事务失败时整笔支付回滚，不会只扣部分。

# 7. 反例或禁止行为

- 禁止在库存不足时继续把库存减为负数。
- 禁止只扣 SKU 库存而不写库存日志。
- 禁止把销量增加放在下单阶段（当前实现是支付成功阶段）。
- 禁止把该规则用于“库存已被预占”的假设。

# 8. 验证方式

1. 记录支付前 SKU 库存、商品库存、销量。
2. 支付成功后重新查询，确认：
   - SKU 库存减少购买数量；
   - 商品库存减少购买数量；
   - 销量增加购买数量；
   - 新增对应库存日志。
3. 构造“库存 1、两个订单各买 1”的场景，依次支付，观察第二笔支付是否成功、库存是否为 0、销量是否增加 2（超卖边界）。
4. 多规格商品购买不同 SKU，确认各 SKU 独立扣减。
5. 同一订单包含两条相同 SKU 明细，确认扣减两次（若接口允许）。

# 9. 来源依据

- `Minishop/backend/app/api/payments.py#L15-L36`：`_deduct_stock` 实现。
- `Minishop/backend/app/api/payments.py#L92-L102`：支付成功调用扣减与消息。
- `Minishop/backend/app/models/models.py#L60-L84`：商品与 SKU 库存、销量字段。
- `Minishop/backend/app/models/models.py#L300-L311`：库存日志字段。

# 10. 未决问题

- 是否应在支付前做库存二次校验并失败？
- 库存截断为 0 是否应记录告警或超卖标记？
- `products.stock` 是否应改为由 SKU 库存汇总计算，避免双写不一致？
- 退款恢复库存时如何避免重复恢复？（跨模块）

> 已确认（2026-11-11，Q-02）：不引入库存预占；超卖为已知限制，库存不足时支付仍成功并以 0 截断。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：逐项扣减序列（before→max(stock-qty,0)→product.stock/sales→InventoryLog 五字段→operator_id=买家）与 _deduct_stock 逐行一致（payments.py:15-36,99）；"库存不足仍支付成功、截断为 0"按已知限制书写并禁止"已预占"假设；退款回减销量属实（admin.py:259）。
- **复核备注**：补记 Q-02 决策。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
