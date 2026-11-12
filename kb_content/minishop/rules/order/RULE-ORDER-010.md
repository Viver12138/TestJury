---
id: RULE-ORDER-010
title: 发货与确认收货的状态约束
knowledge_type: BUSINESS_RULE
project_id: minishop
module_id: order
source_type: OTHER
source_ref: Minishop/backend/app/api/admin.py#L156-L178; Minishop/backend/app/api/orders.py#L247-L260
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
  - shipping
  - confirm
  - state_transition
related_ids:
  - REQ-ORDER-003
  - STATE-ORDER-001
  - API-ORDER-004
  - API-ORDER-006
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 规则陈述

只有管理员可以对状态为 `PAID` 或 `PENDING_SHIPMENT` 的订单发货；只有订单所有者可以对状态为 `SHIPPED` 的订单确认收货。发货写入物流单并通知用户，确认收货把订单置为 `COMPLETED` 且物流单置为 `DELIVERED`。

# 2. 适用范围

- `POST /api/admin/orders/{order_id}/ship`
- `POST /api/orders/{order_id}/confirm`
- 产品版本 `1.0.0`

# 3. 前置条件

- 发货：当前用户 `role=ADMIN`；订单存在；订单状态为 `PAID` 或 `PENDING_SHIPMENT`。
- 确认收货：当前用户是订单所有者；订单状态为 `SHIPPED`。

# 4. 触发条件

管理员提交物流公司/运单号，或用户提交确认收货请求。

# 5. 规则结果

## 发货

- 订单 `status = SHIPPED`，`shipped_at` 为当前时间；
- 若不存在物流单：创建 `shipments` 记录，状态默认 `SHIPPED`；
- 若已存在物流单：更新 `company`、`tracking_number`、`status=SHIPPED`、`shipped_at`；
- 给订单用户写入“订单已发货”站内消息。

## 确认收货

- 订单 `status = COMPLETED`，`completed_at` 为当前时间；
- 对应物流单 `status = DELIVERED`；
- 不发送站内消息。

# 6. 边界与例外

- `PENDING_SHIPMENT` 在代码中没有任何赋值点，实际只有 `PAID` 可发货。
- `company` 和 `tracking_number` 在 Schema 中必填，但没有非空校验，空字符串可发货。
- 非管理员调用发货接口返回 403 `需要管理员权限`。
- 非订单所有者确认收货返回 404 `订单不存在`。
- 重复发货：订单已 `SHIPPED` 时再次发货返回 409。
- 重复确认收货：订单已 `COMPLETED` 时再次确认返回 409。
- 已取消、待支付、退款中的订单不能发货。
- 已发货订单申请退款会使订单进入 `REFUNDING`；退款被拒绝后代码把订单改回 `PAID`，会丢失 `SHIPPED` 状态（见冲突 C-10）。

# 7. 反例或禁止行为

- 禁止跳过支付直接发货。
- 禁止普通用户调用发货接口。
- 禁止对未发货订单确认收货。
- 禁止把 `PENDING_SHIPMENT` 当作已实现状态来设计用例（当前不可达）。
- 禁止用空运单号作为“有效发货”的验收依据，除非项目确认允许。

# 8. 验证方式

1. 对 `PAID` 订单发货，确认状态、物流信息、消息。
2. 对 `PENDING_PAYMENT` 订单发货，预期 409。
3. 普通用户调用发货，预期 403。
4. `SHIPPED` 订单确认收货，确认状态与物流单状态。
5. 对 `PAID` 订单确认收货，预期 409。
6. 重复发货/重复确认，预期 409。
7. 传空字符串物流信息，确认当前行为（已知边界）。

# 9. 来源依据

- `Minishop/backend/app/api/admin.py#L156-L178`：发货状态校验、物流单 upsert、消息。
- `Minishop/backend/app/api/orders.py#L247-L260`：确认收货状态校验与物流单状态。
- `Minishop/backend/app/models/models.py#L233-L243`：物流单字段与状态。

# 10. 未决问题

- 是否应拒绝空物流公司/空运单号？
- `PENDING_SHIPMENT` 应启用还是删除？
- 退款被拒绝后是否应恢复原状态（`SHIPPED`/`COMPLETED`）而不是统一 `PAID`？
- 是否需要自动确认收货？

> 已确认（2026-11-11，Q-04/Q-08/Q-11）：退款拒绝应恢复退款前状态；`PENDING_SHIPMENT` 未启用；后端应拒绝空物流信息。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：发货/确认收货状态约束、物流单 upsert、发货发消息而确认收货不发、PENDING_SHIPMENT 全库仅引用无赋值，均与 admin.py:161-176、orders.py:252-258 一致；空运单号可发货（schemas.py:178-180）与退款拒绝统一回 PAID（admin.py:241）均写为当前缺陷/冲突而非正确规则。
- **复核备注**：补记 Q-04/Q-11 决策：拒绝退款应恢复退款前状态（需 pre_refund_status 快照）；发货应在后端拒绝空物流信息。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
