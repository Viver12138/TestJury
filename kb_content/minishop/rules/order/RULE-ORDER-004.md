---
id: RULE-ORDER-004
title: 用券必须校验归属、状态与有效期
knowledge_type: BUSINESS_RULE
project_id: minishop
module_id: order
source_type: OTHER
source_ref: Minishop/backend/app/api/orders.py#L61-L81; Minishop/backend/app/api/coupons.py#L14-L37
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
  - eligibility
related_ids:
  - REQ-ORDER-001
  - RULE-ORDER-005
  - RULE-ORDER-006
  - API-ORDER-001
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 规则陈述

下单使用优惠券时，用户券必须属于当前用户、券模板为 `ACTIVE`、用户券为 `UNUSED`、且当前时间未超过券的 `end_time`；否则拒绝下单。

# 2. 适用范围

- `POST /api/orders/preview`
- `POST /api/orders`
- 产品版本 `1.0.0`

# 3. 前置条件

- 用户已登录；
- 请求传入 `user_coupon_id`（用户券 ID，不是券模板 ID）。

# 4. 触发条件

订单校验阶段传入非空 `user_coupon_id`。

# 5. 规则结果

| 条件 | 失败结果 |
|---|---|
| 用户券不存在或不属于当前用户 | 400 `优惠券不存在` |
| 券模板不存在或 `status != ACTIVE` | 400 `优惠券无效或已停用` |
| 用户券状态不是 `UNUSED` | 409 `优惠券已使用` |
| 券 `end_time` 非空且当前时间晚于它 | 400 `优惠券已过期` |

通过后进入门槛校验（见 `RULE-ORDER-005`）。

# 6. 边界与例外

- **不校验 `start_time`**：券未到开始时间也可以使用。
- **不校验券类型 `type`**：当前只有 `FULL_REDUCTION`，但代码不限制其他类型。
- **不校验库存/发放量 `total_quantity`**：用券时只看用户券状态。
- 券过期状态是查询时动态计算的，数据库里的 `user_coupons.status` 可能仍是 `UNUSED`；下单时会再按 `end_time` 拒绝。
- 券模板被停用后，已领取的券也不能再使用。
- 不传券时跳过全部校验，`discount_amount=0`。

# 7. 反例或禁止行为

- 禁止使用他人领取的券。
- 禁止重复使用同一张用户券。
- 禁止使用已停用或已过期的券。
- 禁止把券模板 ID 当作 `user_coupon_id` 传入（会返回“优惠券不存在”）。

# 8. 验证方式

1. 使用本人未使用、未过期券，预期成功。
2. 用户 B 使用用户 A 的用户券 ID，预期 400。
3. 使用已使用券，预期 409。
4. 使用已过期券，预期 400。
5. 使用已停用券模板对应的用户券，预期 400。
6. 构造 `start_time` 在未来的券，确认当前实现仍可使用（已知边界）。

# 9. 来源依据

- `Minishop/backend/app/api/orders.py#L61-L81`：用券校验与错误消息。
- `Minishop/backend/app/api/coupons.py#L14-L37`：用户券状态与过期状态计算。
- `Minishop/backend/app/models/models.py#L140-L165`：券模板与用户券字段。

# 10. 未决问题

- 是否应校验 `start_time`？
- 是否应校验券类型与叠加规则？
- 已停用券模板是否应允许已领取用户继续使用？

> 已确认（2026-11-11，Q-06/Q-07）：`total_quantity` 为发放总量；未生效券不应可领用，当前不校验 `start_time` 属已知限制，需经 admin API 造数验证。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：用券校验顺序（归属→券模板 ACTIVE→UNUSED→end_time）与错误消息完全一致（orders.py:62-75）；start_time 不校验、type/total_quantity 不参与用券校验均如实标注为已知边界并列入未决问题。
- **复核备注**：补记 Q-06/Q-07 决策：total_quantity 确认为发放总量（当前三处判断不一致，待修复）；未生效券期望不可领用，当前不校验 start_time 为已知限制；种子数据无未来 start_time 券，需 admin API 造数。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
