---
id: REQ-ORDER-001
title: 订单预览与创建
knowledge_type: REQUIREMENT
project_id: minishop
module_id: order
source_type: REQUIREMENT_SPEC
source_ref: Minishop/README.md#L55-L57; Minishop/backend/app/api/orders.py#L29-L170
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
- create
- preview
- amount
- stock
related_ids:
- RULE-ORDER-001
- RULE-ORDER-002
- RULE-ORDER-003
- RULE-ORDER-004
- RULE-ORDER-005
- RULE-ORDER-006
- FLOW-ORDER-001
- API-ORDER-001
- API-ORDER-002
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: delegated_review_completed
change_reason: 2026-11-12 用户授权技术复核；具体依据见 evidence/M2/delegated_content_review.json
---

# 1. 需求背景与目标

用户从购物车或商品详情选择 SKU 后，需要先看到服务端计算的商品金额、优惠金额和应付金额，再确认生成订单。目标是：

- 所有金额以服务端为准，客户端传入的价格无效；
- 下单前重新校验商品、SKU、库存、地址、优惠券；
- 订单保存商品与地址快照，后续商品改价或地址修改不影响历史订单。

# 2. 用户与前置条件

- 用户已登录，持有有效 JWT；
- 用户至少有一个归属自己的收货地址（创建订单时必填；预览时可选）；
- 目标 SKU 存在且 `status=ACTIVE`，所属商品 `status=ON_SALE`；
- 购买数量 ≥ 1 且不超过该 SKU 的库存；
- 如使用优惠券：券归属当前用户、未被使用、未过期、订单商品金额达到门槛。

# 3. 功能描述

## 3.1 订单预览 `POST /api/orders/preview`

接收商品项、可选地址、可选用户券，返回服务端计算的明细与金额，**不产生任何副作用**（不建单、不占券、不扣库存、不清购物车）。

## 3.2 创建订单 `POST /api/orders`

在预览校验的基础上要求 `address_id` 必填，创建状态为 `PENDING_PAYMENT` 的订单，保存地址与商品快照；如使用优惠券，立即把用户券置为 `USED` 并累加券的 `used_quantity`。

# 4. 主成功场景

1. 用户选择 1 个或多个 SKU 及数量。
2. 调用预览，得到 `total_amount`、`discount_amount`、`pay_amount` 和商品明细。
3. 用户选择地址与优惠券，再次预览确认金额。
4. 调用创建订单，返回 201 与订单对象。
5. 订单状态为 `PENDING_PAYMENT`，金额、地址、商品快照已落库。
6. 用户进入支付页创建支付单（见 `REQ-ORDER-002`）。

# 5. 异常与替代场景

| 场景 | 预期结果 |
|---|---|
| `items` 为空 | 400 `订单商品不能为空` |
| 数量 < 1 | 400 `购买数量不能小于 1` |
| SKU 不存在或 `status != ACTIVE` | 400 `商品规格无效` |
| 商品不存在或已下架 | 400 `商品已下架` |
| 数量 > SKU 库存 | 409 `商品「<名称>」库存不足` |
| 预览传入非本人地址 | 400 `收货地址不存在` |
| 创建订单 `address_id=0` | 400 `请选择收货地址` |
| 创建订单缺少/null/类型非法 `address_id` | 400 `VALIDATION_ERROR` |
| 优惠券不属于当前用户 | 400 `优惠券不存在` |
| 优惠券停用 | 400 `优惠券无效或已停用` |
| 优惠券已使用 | 409 `优惠券已使用` |
| 优惠券已过期 | 400 `优惠券已过期` |
| 未达券门槛 | 409 `未达优惠券门槛（满<X>可用）` |

上述业务错误都返回 HTTP 4xx，响应包络为 `{"code": "HTTP_ERROR", "message": "<消息>", "data": null}`。请求体字段缺失/类型错误由 FastAPI 返回 400 `VALIDATION_ERROR`。

# 6. 输入与输出

## 输入

| 字段 | 类型 | 必填 | 说明 |
|---|---|:---:|---|
| `items` | array | 是 | 至少 1 项 |
| `items[].sku_id` | int | 是 | 目标 SKU |
| `items[].quantity` | int | 否 | 默认 1 |
| `address_id` | int | 预览否 / 创建是 | 必须归属当前用户 |
| `user_coupon_id` | int | 否 | 用户券 ID，不是优惠券模板 ID |
| `payment_method` | string | 否 | 创建订单接口接受但**当前未使用**，支付方式在创建支付单时决定 |

## 输出（创建订单，201）

`data` 为订单对象，包含 `id`、`order_no`、`status`、`status_cn`、`total_amount`、`discount_amount`、`pay_amount`、`receiver_name`、`phone`、`address_snapshot`、`user_coupon_id`、`items[]`、时间字段。

# 7. 业务约束

- 金额只使用 `product_skus.price`，不读取客户端价格，也不使用 `products.price` 作为成交价。
- 商品总金额 = Σ(`sku.price × quantity`)；
- 优惠金额 = 所用券的 `discount_amount`（固定金额）；
- 应付金额 = `max(总金额 - 优惠金额, 0)`，四舍五入到 2 位；
- 库存校验只针对 `product_skus.stock`，不校验聚合字段 `products.stock`；
- 创建订单**不扣减库存**，也不锁定库存；
- 创建订单**不清空购物车**；
- 立即购买=加购后跳转 `/cart`，不支持直接结算（Q-01 已确认）；因加购对同 SKU 累加，连续“立即购买”可能使结算数量翻倍，超过库存时返回 400 `库存不足，无法合并`（Q-03）。
- 创建订单**没有幂等键**，重复提交会生成多张订单；
- 地址与商品信息以快照形式写入订单，后续源数据变化不影响已创建订单。

# 8. 验收标准

1. 同一组商品且期间价格/券不变时，创建金额应等于预览值按落库规则 round 到 2 位；预览 total_amount/discount_amount 可能含浮点尾差。价格变化后创建按新价格重新计算。
2. 客户端伪造价格字段不会影响订单金额。
3. 数量等于库存时允许下单；数量为库存 +1 时返回 409。
4. 未上架商品、失效 SKU 不能下单。
5. 使用本人未使用且未过期、达到门槛的券，订单优惠金额等于券面额。
6. 使用他人券、已用券、过期券、未达门槛券均被拒绝，且错误消息可区分。
7. 创建成功后订单状态为 `PENDING_PAYMENT`，地址快照与商品快照完整。
8. 创建成功后该用户券状态变为 `USED`，`used_order_id` 指向新订单。
9. 创建订单前后 SKU 库存与商品销量**不变**。
10. 创建订单前后购物车内容**不变**。

# 9. 明确不支持的行为

- 不预占/锁定库存；
- 不自动合并购物车同 SKU（由购物车模块负责）；
- 不清空已下单商品；
- 不支持幂等提交、防重复下单；
- 不支持订单超时自动关闭；
- 不支持发票、备注、多地址、拆单；
- 不支持价格锁定：预览后商品改价，创建时按最新 `sku.price` 计算。

# 10. 未决问题

- 下单后购物车是否应清空？（当前不清理，可能与用户预期不符）
- 是否应引入库存预占或支付时库存二次校验？（当前存在超卖风险）
- 重复提交是否应返回同一订单（幂等键）？
- 是否需要订单超时关闭任务？
- `PENDING_SHIPMENT` 状态在代码中被引用但从未赋值，是否应删除或启用？


# 本次授权技术复核适用性

核对 orders.py 创建/预览无库存扣减、无清购物车、用券即占用；修正预览与落库金额断言需考虑精度及重新计价。

本次结论基于冻结快照与既有决策，当前实现中的限制不代表目标规格；已决策但未实施的项目仍按治理台账单独跟踪。复核者为用户授权的 AI 代理，非新增人工签署。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：修改后通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：异常表把"缺少 address_id"归为业务 400「请选择收货地址」不准确：address_id 为必填 int（schemas.py:147），缺失/null 被 RequestValidationError 拦截返回 400 VALIDATION_ERROR「参数校验失败」（main.py:47-52，已独立复核），仅 address_id=0 命中 orders.py:118-119。其余陈述（不预占库存、不清购物车、无超时关闭、PENDING_SHIPMENT 从未赋值）与代码一致。
- **复核备注**：修订要求：拆分为"address_id=0 → 400 请选择收货地址"与"缺少 address_id → 400 VALIDATION_ERROR"；并补记 Q-01（立即购买=加购+跳转购物车）与 Q-03（不清空购物车及其连锁影响）决策。
- **回写说明**：2026-11-12 已按复核意见回写；仍为 in_review，待复审后置 approved。
