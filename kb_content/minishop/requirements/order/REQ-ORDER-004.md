---
id: REQ-ORDER-004
title: 订单取消
knowledge_type: REQUIREMENT
project_id: minishop
module_id: order
source_type: REQUIREMENT_SPEC
source_ref: Minishop/README.md#L57-L58; Minishop/backend/app/api/orders.py#L223-L244
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
related_ids:
  - RULE-ORDER-007
  - STATE-ORDER-001
  - API-ORDER-004
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 需求背景与目标

用户在下单后、支付前可能改变主意，需要取消订单。取消后订单进入终态，已占用的优惠券应归还，用户可以继续用该券下单。

# 2. 用户与前置条件

- 用户已登录，且是订单所有者；
- 订单状态为 `PENDING_PAYMENT`。

# 3. 功能描述

`POST /api/orders/{order_id}/cancel`：

- 将订单状态置 `CANCELLED`，记录 `cancelled_at`；
- 若订单使用了优惠券，将用户券恢复为 `UNUSED`，清空 `used_order_id` 与 `used_at`，并把券模板的 `used_quantity` 减 1（不小于 0）；
- 不处理库存（下单本就没有扣减）；
- 不处理支付单（若已创建 `PENDING` 支付单，记录保留）。

# 4. 主成功场景

1. 用户打开待支付订单详情。
2. 点击“取消订单”并确认。
3. 返回 200，订单状态变为 `CANCELLED`。
4. 订单详情显示“已取消”，不再提供支付入口。
5. 若使用过优惠券，“我的优惠券”中该券恢复为可用。

# 5. 异常与替代场景

| 场景 | 预期结果 |
|---|---|
| 订单不存在 | 404 `订单不存在` |
| 非订单所有者 | 404 `订单不存在`（不暴露存在性） |
| 订单已支付/已发货/已完成/已取消/退款中/已退款 | 409 `只有待支付订单可以取消` |
| 取消后再次取消 | 409（状态已非待支付） |
| 取消后尝试支付 | 409 `订单已取消，无法支付` |

# 6. 输入与输出

| 项 | 内容 |
|---|---|
| 入参 | 无 |
| 成功输出 | 200，`message: "订单已取消"`，`data: null` |
| 副作用 | 订单 `CANCELLED`；用户券恢复；券模板 `used_quantity` 减 1 |

# 7. 业务约束

- 只有待支付订单可以取消；已支付订单必须走退款流程。
- 取消不要求填写原因。
- 管理员没有取消订单的专用接口。
- 取消是终态，不可恢复。
- 取消不扣减库存，也不恢复库存（因为下单未扣库存）。

# 8. 验收标准

1. 待支付订单取消成功，状态为 `CANCELLED`，`cancelled_at` 非空。
2. 非本人取消返回 404。
3. 已支付订单取消返回 409，状态不变。
4. 取消后优惠券恢复为 `UNUSED`，可再次用于下单。
5. 取消后券模板 `used_quantity` 正确回退，且不会小于 0。
6. 取消后再次支付返回 409。

# 9. 明确不支持的行为

- 取消已支付订单（应走退款）；
- 取消原因、取消备注；
- 管理员代取消；
- 订单超时自动取消；
- 取消后恢复库存（当前无库存占用）。

# 10. 未决问题

- 是否需要订单超时自动取消？
- 已创建 `PENDING` 支付单后取消订单，支付单是否应同步关闭或标记失效？
- 优惠券归还后，券的有效期是否应顺延？（当前不顺延）

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：仅 PENDING_PAYMENT 可取消、非本人返回 404、优惠券归还 UNUSED 且 used_quantity 回退下限 0、不动库存与支付单，均与 orders.py:226-242 一致；未假设存在超时自动取消。
- **复核备注**：补记 Q-12 决策：确认当前无超时自动取消，用例不得断言自动取消。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
