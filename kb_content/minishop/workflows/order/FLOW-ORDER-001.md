---
id: FLOW-ORDER-001
title: 下单到确认收货主流程
knowledge_type: WORKFLOW
project_id: minishop
module_id: order
source_type: OTHER
source_ref: Minishop/README.md#L54-L58; Minishop/frontend/src/pages/cart/Cart.tsx#L45-L51; Minishop/frontend/src/pages/order/OrderConfirm.tsx#L19-L62; Minishop/frontend/src/pages/payment/Payment.tsx#L18-L33; Minishop/backend/app/api/orders.py#L88-L260
source_version: snapshot-2026-11-11
product_version:
  - "1.0.0"
platforms:
  - all
evidence_level: E2
status: in_review
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
  - flow
  - checkout
  - payment
  - fulfillment
related_ids:
  - REQ-ORDER-001
  - REQ-ORDER-002
  - REQ-ORDER-003
  - REQ-ORDER-004
  - STATE-ORDER-001
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: changes_applied_pending_reapproval
change_reason: "2026-11-12 人工复核回写（审核结论：修改后通过）"
---

# 1. 流程目标

把用户选中的 SKU 转成订单，完成模拟支付、管理员发货和用户确认收货，使订单从 `PENDING_PAYMENT` 推进到 `COMPLETED`。

# 2. 参与角色

| 角色 | 职责 |
|---|---|
| 普通用户 `USER` | 加购、选地址/券、提交订单、支付、确认收货 |
| 管理员 `ADMIN` | 查看订单、录入物流并发货 |
| 系统 | 金额重算、库存扣减、状态推进、站内消息 |

# 3. 前置条件

- 用户已登录且账号 `ACTIVE`；
- 用户有收货地址；
- 目标 SKU 存在、商品上架、SKU 库存满足购买数量；
- 若用券：券属于本人、未使用、未过期、达到门槛；
- 管理员账号可登录后台。

# 4. 主流程

| 步骤 | 操作者 | 动作 | 系统响应 | 状态变化 | 可观察结果 |
|---:|---|---|---|---|---|
| 1 | 用户 | 在商品详情/列表选择 SKU 并加购 | `POST /api/cart/items` 返回 201 | 无订单状态 | 购物车出现该 SKU，数量合并 |
| 2 | 用户 | 在购物车勾选商品并点击“去结算” | 前端把 `sku_id + quantity` 写入 `sessionStorage`，跳转 `/orders/confirm` | 无 | 结算页显示商品清单 |
| 3 | 用户 | 选择地址、优惠券 | `POST /api/orders/preview` 返回 200 与金额 | 无 | 页面显示商品金额、优惠、应付 |
| 4 | 用户 | 点击“提交订单” | `POST /api/orders` 返回 201 | `(新建) → PENDING_PAYMENT` | 跳转支付页，订单详情可见 |
| 5 | 用户 | 在支付页点击“模拟支付” | `POST /api/payments` 返回 201，`status=PENDING` | 无订单状态变化 | 生成支付单号与待支付记录 |
| 6 | 用户 | 选择“模拟支付成功” | `POST /api/payments/{id}/success` 返回 200 | `PENDING_PAYMENT → PAID` | 订单已支付；库存减少；销量增加；收到站内消息 |
| 7 | 管理员 | 在后台对已支付订单点击发货，填写物流公司/运单号 | `POST /api/admin/orders/{id}/ship` 返回 200 | `PAID → SHIPPED` | 订单详情出现物流信息；用户收到站内消息 |
| 8 | 用户 | 在订单详情点击“确认收货” | `POST /api/orders/{id}/confirm` 返回 200 | `SHIPPED → COMPLETED` | 订单已完成；物流状态已签收 |
| 9 | 用户 | 对已完成订单发表评价（跨模块） | `POST /api/reviews` 返回 201 | 订单状态不变 | 商品评价列表出现该评价 |

> **UI 交互说明（复核 2026-11-11）**：第 5、6 步由支付页一次点击连续触发两个请求（`create` + `success` 或 `create` + `fail`），中间没有独立选择界面；UI 用例不要把两步写成两次点击。

# 5. 分支流程

## 5.1 支付失败

1. 用户在第 5 步后点击“模拟支付失败”。
2. `POST /api/payments/{id}/fail` 返回 200。
3. 支付单 `FAILED`，订单仍为 `PENDING_PAYMENT`。
4. 用户可重新创建支付单并支付；旧 `FAILED` 记录保留。

## 5.2 取消订单

1. 订单仍为 `PENDING_PAYMENT` 时，用户点击取消。
2. `POST /api/orders/{id}/cancel` 返回 200。
3. 订单 `CANCELLED`；优惠券恢复 `UNUSED`；购物车不受影响。
4. 取消后不能支付，也不能恢复。

## 5.3 退款（跨模块，未纳入本批知识）

订单 `PAID/SHIPPED/COMPLETED` 可申请退款，订单进入 `REFUNDING`；管理员同意后 `REFUNDED` 并恢复库存；拒绝后当前回 `PAID`（已确认应恢复退款前状态，Q-04，属缺陷待修复）。详见 `after_sales` 模块（本批未覆盖）。

# 6. 异常流程

| 异常 | 触发点 | 系统响应 | 用户可见结果 |
|---|---|---|---|
| 未登录 | 任意受保护接口 | 401 `未登录` / `登录已过期` | 跳转登录页 |
| 账号禁用 | 任意受保护接口 | 403 `账号已被禁用` | 无法继续操作 |
| 商品下架 | 预览/创建订单 | 400 `商品已下架` | 提示商品不可购买 |
| SKU 失效 | 预览/创建订单 | 400 `商品规格无效` | 提示规格无效 |
| 库存不足 | 预览/创建订单 | 409 `商品「X」库存不足` | 提示库存不足 |
| 地址缺失 | 创建订单 | 400 `请选择收货地址` | 提示先选地址 |
| 地址非本人 | 预览/创建订单 | 400 `收货地址不存在` | 提示地址无效 |
| 券不可用 | 预览/创建订单 | 400/409（见 `RULE-ORDER-004`） | 提示券不可用 |
| 未达门槛 | 预览/创建订单 | 409 `未达优惠券门槛（满X可用）` | 提示门槛 |
| 订单已取消 | 创建支付/支付成功 | 409 `订单已取消，无法支付` | 无法支付 |
| 重复支付 | 支付成功 | 409 `订单已支付，请勿重复支付` | 不重复扣款 |
| 非法发货 | 发货 | 409 `只有已支付/待发货的订单可以发货` | 后台报错 |
| 非法确认 | 确认收货 | 409 `只有已发货订单可以确认收货` | 前台报错 |

# 7. 回退、取消与重试

| 场景 | 是否支持 | 说明 |
|---|---|---|
| 支付失败后重试 | ✅ | 新建支付单，旧记录保留 |
| 待支付取消 | ✅ | 券归还，订单终态 |
| 已支付取消 | ❌ | 只能走退款 |
| 退款被拒绝后重试退款 | ❌ | 同一订单已有退款记录时再次申请返回 409 |
| 发货撤销 | ❌ | 无接口 |
| 确认收货撤销 | ❌ | 无接口 |
| 订单超时自动取消 | ❌ | 无定时任务 |
| 重复提交订单 | ⚠️ | 无幂等，可能生成多张订单 |

# 8. 涉及的业务规则

- `RULE-ORDER-001` 服务端金额重算
- `RULE-ORDER-002` 地址归属与快照
- `RULE-ORDER-003` SKU/商品/库存校验
- `RULE-ORDER-004` 用券资格
- `RULE-ORDER-005` 门槛与应付金额
- `RULE-ORDER-006` 创建订单副作用
- `RULE-ORDER-007` 取消与券归还
- `RULE-ORDER-008` 支付金额与重复支付
- `RULE-ORDER-009` 支付成功扣库存
- `RULE-ORDER-010` 发货与确认收货
- `RULE-ORDER-011` 订单访问控制

# 9. 涉及的接口与数据

| 用途 | 接口 |
|---|---|
| 加购 | `POST /api/cart/items` |
| 预览 | `POST /api/orders/preview` |
| 创建 | `POST /api/orders` |
| 查询 | `GET /api/orders`、`GET /api/orders/{id}` |
| 支付 | `POST /api/payments`、`/success`、`/fail` |
| 发货 | `POST /api/admin/orders/{id}/ship` |
| 确认 | `POST /api/orders/{id}/confirm` |
| 数据 | `orders`、`order_items`、`payments`、`shipments`、`user_coupons`、`inventory_logs` |

详见 `interfaces/order/`。

# 10. 未决问题

- 前端结算依赖 `sessionStorage`，刷新/直接访问 `/orders/confirm` 会丢失商品清单；是否应改为服务端购物车结算？
- 下单后购物车是否应清空？
- 是否需要订单超时关闭与库存预占？
- 退款拒绝后的状态恢复（`SHIPPED`/`COMPLETED` 丢失）应如何定义？
- 是否需要管理员取消订单能力？

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：修改后通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：主流程步骤/接口/状态码/异常文案与代码一致，后端确无调度器（"无超时自动取消"属实）。但第 5/6 步把支付描述为两次交互，设计者独立复核 Payment.tsx:18-33 证实：一次点击即顺序触发 create+success（或 create+fail）两个请求，中间无选择界面——按文档写 UI 用例会因找不到中间步骤而失败，故判定由"通过"上调为"修改后通过"。
- **复核备注**：修订要求：合并第 5/6 步或注明"一次点击依次触发两个 API"；异常表"未达门槛"文案补全为"未达优惠券门槛（满X可用）"（orders.py:78）；补记 Q-12 决策。
- **回写说明**：2026-11-12 已按复核意见回写；仍为 in_review，待复审后置 approved。
