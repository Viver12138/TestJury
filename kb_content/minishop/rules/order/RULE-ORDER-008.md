---
id: RULE-ORDER-008
title: 支付金额来源、重复支付保护与失败重试
knowledge_type: BUSINESS_RULE
project_id: minishop
module_id: order
source_type: OTHER
source_ref: Minishop/backend/app/api/payments.py#L39-L118
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
change_reason: 2026-11-12 用户授权技术复核；具体依据见 evidence/M2/delegated_content_review.json
tags:
- order
- payment
- idempotency
- duplicate_payment
related_ids:
- REQ-ORDER-002
- RULE-ORDER-009
- API-ORDER-005
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: delegated_review_completed
---

# 1. 规则陈述

支付金额只能取自服务端订单的 `pay_amount`；已支付或已进入后续状态的订单不得重复支付；支付失败后订单仍为待支付，允许重新创建支付单并再次支付。

# 2. 适用范围

- `POST /api/payments`
- `POST /api/payments/{payment_id}/success`
- `POST /api/payments/{payment_id}/fail`
- 产品版本 `1.0.0`

# 3. 前置条件

- 用户已登录且是订单所有者；
- 订单存在；
- 对 `success` / `fail`：支付单存在（否则 404 `支付记录不存在`），且支付单所属订单归属当前用户（否则 404 `订单不存在`）。

# 4. 触发条件

用户创建支付单、标记支付成功或标记支付失败。

# 5. 规则结果

## 创建支付单

- 订单状态为 `CANCELLED`：409 `订单已取消，无法支付`；
- 订单状态为 `PAID`、`PENDING_SHIPMENT`、`SHIPPED`、`COMPLETED`：409 `订单已支付，请勿重复支付`；
- 订单状态为 `REFUNDING`、`REFUNDED`：409 `订单已进入售后流程`；
- 已存在 `PENDING` 支付单：直接返回该支付单，不新建；
- 否则新建支付单，`amount = order.pay_amount`，`status = PENDING`。

## 支付成功

- 订单状态属于 `PAID`、`PENDING_SHIPMENT`、`SHIPPED`、`COMPLETED`、`REFUNDING`、`REFUNDED`：409 `订单已支付，请勿重复支付`；
- 订单状态为 `CANCELLED`：409 `订单已取消，无法支付`；
- 否则把支付单金额改写为订单 `pay_amount`，支付单 `SUCCESS`，订单 `PAID`，并触发库存扣减（`RULE-ORDER-009`）。

## 支付失败

- 仅当订单为 `PENDING_PAYMENT` 时允许；
- 支付单置 `FAILED`，订单状态不变；
- 用户可再次创建支付单。

# 6. 边界与例外

- 支付成功**不校验支付单当前状态**，`FAILED` 支付单在订单仍待支付时也能被标记成功。
- `method` 无枚举校验，任意字符串可传入；默认 `WECHAT`。
- 同一订单可存在多条支付记录（失败后重试），但订单只有一个 `payment` 单对象关系且未排序。Q-05 原复核记录在 FAILED + SUCCESS 场景观察到返回第一条 FAILED 并产生 SAWarning；不得把未排序关系当作稳定选择契约。
- 目标行为（Q-05 已确认）：订单详情展示成功/最新支付记录。当前源码尚未落实该目标，应作为已确认缺陷记录。
- “重复支付保护”依赖订单状态，不是支付单状态；并发下两个请求可能都读到 `PENDING_PAYMENT`，缺少数据库行锁。
- 创建支付单的“幂等”只覆盖已存在 `PENDING` 支付单的情况，不覆盖 `FAILED`。

# 7. 反例或禁止行为

- 禁止客户端指定或覆盖支付金额。
- 禁止对已支付订单再次扣款或重复扣库存。
- 禁止把支付失败当作订单失败（订单仍可支付）。
- 禁止把 `FAILED` 支付单直接当作已退款或已关闭。

# 8. 验证方式

1. 创建支付单，核对金额等于订单 `pay_amount`。
2. 连续创建两次，确认第二次返回同一 `PENDING` 支付单。
3. 支付成功，确认订单 `PAID`、支付单 `SUCCESS`。
4. 再次调用成功，确认 409 且库存不重复扣减。
5. 支付失败后再次支付，确认成功。
6. 对已取消订单创建支付，确认 409。
7. 对 `FAILED` 支付单调用成功（订单仍待支付），确认当前行为。

# 9. 来源依据

- `Minishop/backend/app/api/payments.py#L39-L74`：创建支付与状态门禁。
- `Minishop/backend/app/api/payments.py#L77-L103`：支付成功、金额来源与状态推进。
- `Minishop/backend/app/api/payments.py#L106-L118`：支付失败。

# 10. 未决问题

- 是否应校验 `payment.status`，禁止 `FAILED -> SUCCESS`？
- 多支付记录的展示规则已经由 Q-05 裁决；关系修复与回归验证仍待完成。
- 是否需要支付幂等键与并发锁？
- `method` 是否应限定为 `WECHAT` / `ALIPAY`？

> 已确认（2026-11-11，Q-05）：订单详情应展示成功/最新支付；当前 `Order.payment` 单对象关系为确定性缺陷（恒返回第一条 FAILED 并抛 SAWarning）。

> 2026-11-12 整改说明：以上是原复核的场景观察，不能推导 SQL 无排序时对任意数据均“恒返回第一条”。本轮同步当前实现与目标规则后退回 `in_review`；原审核记录保留为历史，不代表本次正文已复审。


# 本次授权技术复核适用性

核对支付门禁、金额取 order.pay_amount、PENDING 复用及失败重试；没有支付状态与并发行锁保障；多支付选择不是排序契约。

本次结论基于冻结快照与既有决策，当前实现中的限制不代表目标规格；已决策但未实施的项目仍按治理台账单独跟踪。复核者为用户授权的 AI 代理，非新增人工签署。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：创建/成功/失败三接口状态门禁与消息、PENDING 支付单幂等复用仅覆盖 PENDING、不校验 payment.status、无并发行锁、method 无枚举校验，均与 payments.py:44-59,65,87-99,114-117 一致；单对象 payment 展示问题写成缺陷并列未决。
- **复核备注**：补记 Q-05 实测：Order.payment 恒取第一条 FAILED（SAWarning），修复方向为多对象排序或 current_payment_id。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
