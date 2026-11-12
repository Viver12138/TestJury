---
id: RULE-ORDER-006
title: 创建订单的落库内容与副作用边界
knowledge_type: BUSINESS_RULE
project_id: minishop
module_id: order
source_type: OTHER
source_ref: Minishop/backend/app/api/orders.py#L116-L170; Minishop/backend/app/api/common.py#L19-L20
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
  - create
  - side_effect
  - snapshot
  - coupon
related_ids:
  - REQ-ORDER-001
  - RULE-ORDER-007
  - RULE-ORDER-009
  - FLOW-ORDER-001
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 规则陈述

创建订单时，系统写入状态为 `PENDING_PAYMENT` 的订单与订单明细、保存地址和商品快照、占用优惠券；但**不扣减库存、不清空购物车、不创建支付单**。

# 2. 适用范围

- `POST /api/orders`
- 产品版本 `1.0.0`

# 3. 前置条件

- 已通过 `RULE-ORDER-001` ~ `RULE-ORDER-005` 的全部校验；
- `address_id` 有效且归属当前用户。

# 4. 触发条件

创建订单校验全部通过并提交事务。

# 5. 规则结果

## 订单主表

- `order_no`：`YYYYMMDDHHMMSS` + 6 位随机数，唯一索引；
- `status = PENDING_PAYMENT`；
- `total_amount`、`discount_amount`、`pay_amount` 为服务端计算值；
- `receiver_name`、`phone`、`address_snapshot` 为地址快照；
- `user_coupon_id` 为所用用户券 ID，未用券为 0；
- 时间字段：`created_at` 自动生成，其余完成时间字段为空。

## 订单明细

每一项保存 `product_id`、`sku_id`、商品名称快照、规格快照、成交单价、数量、小计。

## 优惠券

- 用户券 `status = USED`；
- `used_order_id = 新订单 ID`；
- `used_at` 为当前时间；
- 券模板 `used_quantity += 1`。

## 不发生的副作用

- 不修改 `product_skus.stock`；
- 不修改 `products.stock`、`products.sales`；
- 不删除或修改购物车项；
- 不创建支付记录；
- 不发送站内消息。

# 6. 边界与例外

- 无幂等键：相同请求重复提交会创建多张订单，各自占用各自的券（若同一张券第二次提交，会因券已 `USED` 返回 409）。
- 订单号随机后缀理论上可能碰撞，数据库唯一索引会拒绝，但接口未捕获该异常，可能返回 500。
- 未使用优惠券时，`user_coupon_id=0`，不产生券占用。
- 事务包含订单、明细、券更新；若中途异常，依赖数据库事务回滚。

# 7. 反例或禁止行为

- 禁止在创建订单阶段扣库存或占库存（当前没有实现，也不应被用例假设为已实现）。
- 禁止在创建订单阶段清空购物车。
- 禁止把订单金额在落库后再次按商品现价重算。

# 8. 验证方式

1. 创建订单后查询 `orders`、`order_items`、`user_coupons`、`coupons.used_quantity`。
2. 对比创建前后 SKU 库存、商品销量、购物车记录，确认均未变化。
3. 重复提交同一请求（无券），确认生成两张订单。
4. 使用同一张券连续提交两次，第二次预期 409。
5. 查询订单详情，核对地址快照与商品名称/规格快照。

# 9. 来源依据

- `Minishop/backend/app/api/orders.py#L116-L170`：创建订单、明细、券占用。
- `Minishop/backend/app/api/common.py#L19-L20`：订单号生成规则。
- `Minishop/backend/app/api/payments.py#L15-L36`：库存扣减发生在支付成功，而非下单。

# 10. 未决问题

- 下单后是否应清空购物车？
- 是否需要幂等键防止重复下单？
- 券占用与订单创建是否需要在同一事务中强制成功？

> 已确认（2026-11-11，Q-03）：下单不清空购物车；立即购买=加购，同 SKU 累加，重复操作可能导致数量翻倍/超库存 400。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：落库字段与券占用副作用（orders.py:124-166）、以及"不扣库存/不清购物车/不建支付单/不发消息"边界均一致；前端下单后仅清 sessionStorage（OrderConfirm.tsx:51-58）；订单号唯一索引冲突未捕获可致 500 亦属实（common.py:19-20；models.py:175；main.py:27-32）。
- **复核备注**：补记 Q-03 决策：不清空购物车为当前行为，但须写明"立即购买=加购 + 同 SKU 数量累加（cart.py:65-75）"导致的重复购买数量翻倍/超库存 400 连锁限制。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
