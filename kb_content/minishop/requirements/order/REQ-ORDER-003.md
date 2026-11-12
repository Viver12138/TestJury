---
id: REQ-ORDER-003
title: 发货与确认收货
knowledge_type: REQUIREMENT
project_id: minishop
module_id: order
source_type: REQUIREMENT_SPEC
source_ref: Minishop/README.md#L65-L66; Minishop/backend/app/api/admin.py#L156-L178; Minishop/backend/app/api/orders.py#L247-L260
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
  - logistics
  - confirm
related_ids:
  - RULE-ORDER-010
  - STATE-ORDER-001
  - API-ORDER-004
  - API-ORDER-006
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 需求背景与目标

订单支付后由管理员发货并录入物流信息；用户收到货后确认收货，订单完成。该流程用于验证订单状态机的后半段和物流信息的可观察性。

# 2. 用户与前置条件

- 发货：操作者必须是 `ADMIN`；订单状态为 `PAID` 或 `PENDING_SHIPMENT`。
- 确认收货：操作者必须是订单所有者；订单状态为 `SHIPPED`。

# 3. 功能描述

## 3.1 管理员发货 `POST /api/admin/orders/{order_id}/ship`

- 入参：物流公司 `company`、运单号 `tracking_number`。
- 订单状态置 `SHIPPED`，记录 `shipped_at`。
- 若不存在物流单则创建；已存在则更新公司、运单号、状态与发货时间。
- 给订单用户发送“订单已发货”站内消息。

## 3.2 确认收货 `POST /api/orders/{order_id}/confirm`

- 订单状态置 `COMPLETED`，记录 `completed_at`。
- 对应物流单状态置 `DELIVERED`。

# 4. 主成功场景

1. 管理员在后台选择已支付订单，填写物流公司与运单号并提交。
2. 返回 200，订单状态为 `SHIPPED`。
3. 用户在订单详情看到物流公司、运单号、物流状态“已发货”。
4. 用户点击“确认收货”，返回 200，订单状态为 `COMPLETED`。
5. 物流状态变为“已签收”，订单可进入评价流程。

# 5. 异常与替代场景

| 场景 | 预期结果 |
|---|---|
| 普通用户调用发货接口 | 403 `需要管理员权限` |
| 订单不存在 | 404 `订单不存在` |
| 对 `PENDING_PAYMENT` / `CANCELLED` / `SHIPPED` / `COMPLETED` 订单发货 | 409 `只有已支付/待发货的订单可以发货` |
| 非订单所有者确认收货 | 404 `订单不存在` |
| 对非 `SHIPPED` 订单确认收货 | 409 `只有已发货订单可以确认收货` |
| 重复确认收货 | 409（第二次时状态已为 `COMPLETED`） |

# 6. 输入与输出

| 接口 | 入参 | 成功输出 |
|---|---|---|
| 管理员发货 | `company: string`、`tracking_number: string` | 200，`data: {order_id, status: "SHIPPED"}` |
| 确认收货 | 无 | 200，`data: null` |

## 字段约束

- `company` 与 `tracking_number` 在 Schema 中为必填字符串，但**没有非空校验**，传入空字符串 `""` 也能通过。
- 没有物流公司枚举、运单号格式校验。

# 7. 业务约束

- 发货与确认收货都依赖订单当前状态，不允许跳状态。
- 发货只允许 `PAID` 或 `PENDING_SHIPMENT`；`PENDING_SHIPMENT` 在代码中从未被赋值，因此实际只有 `PAID` 可发货。
- 确认收货只允许 `SHIPPED`。
- 发货会给用户产生站内消息；确认收货不发消息。
- 确认收货不触发其他业务（不结算、不积分、不自动评价）。

# 8. 验收标准

1. 管理员可对 `PAID` 订单发货，订单变为 `SHIPPED`，物流信息与入参一致。
2. 普通用户调用发货接口返回 403。
3. 对未支付订单发货返回 409，状态不变。
4. 发货后订单详情包含物流公司、运单号、物流状态。
5. 用户可对 `SHIPPED` 订单确认收货，订单变为 `COMPLETED`，物流状态变为 `DELIVERED`。
6. 对未发货订单确认收货返回 409。
7. 重复确认收货返回 409。
8. 发货后用户收到站内消息。

# 9. 明确不支持的行为

- 真实物流轨迹查询与推送；
- 部分发货、拆包裹、多运单；
- 修改收货地址；
- 自动确认收货（超时）；
- 拒收、退货物流、换货；
- 发货撤销。

# 10. 未决问题

- 空物流公司与空运单号是否应被拒绝？
- `PENDING_SHIPMENT` 是否应启用为“已支付待发货”状态？
- 退款中的订单是否允许发货？（当前 `ship_order` 只检查 `PAID/PENDING_SHIPMENT`，`REFUNDING` 会被拒绝）
- 确认收货后是否应自动流转到评价提醒或结算？

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：发货门禁 PAID/PENDING_SHIPMENT、非管理员 403、确认收货仅 SHIPPED→COMPLETED 且物流置 DELIVERED 均与代码一致（admin.py:157-176；orders.py:250-258；dependencies.py:57）；空 company/tracking_number 可通过被如实写为当前缺陷。
- **复核备注**：补记 Q-11 决策：后端应拒绝空物流信息（前端 AdminOrders.tsx:38,107-108 已有必填校验，风险仅在 API 层）。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
