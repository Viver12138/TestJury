---
id: API-ORDER-001
title: 订单预览接口
knowledge_type: INTERFACE
project_id: minishop
module_id: order
source_type: API_SPEC
source_ref: Minishop/backend/app/api/orders.py#L88-L113; Minishop/backend/app/schemas/schemas.py#L134-L143
source_version: snapshot-2026-11-11
product_version:
  - "1.0.0"
platforms:
  - all
evidence_level: E2
status: approved
owner: minishop_project_team
reviewer: "平台设计者（技术负责人）"
created_at: 2026-11-11
updated_at: 2026-11-12
effective_from: null
effective_until: null
reviewed_at: 2026-11-11
review_cycle_days: 90
tags:
  - order
  - preview
  - api
related_ids:
  - REQ-ORDER-001
  - RULE-ORDER-001
  - RULE-ORDER-003
  - API-ORDER-002
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 接口用途

在下单前由服务端重新计算商品金额、优惠金额和应付金额，并校验 SKU、库存、地址、优惠券；不创建订单、不产生任何持久化副作用。

# 2. 请求方式与路径

```http
POST /api/orders/preview
Authorization: Bearer <JWT>
Content-Type: application/json
```

# 3. 身份认证与权限

- 必须登录；无 token/无效 token 返回 401。
- 只能使用自己的地址和用户券。
- 无角色限制（`USER`、`ADMIN` 均可调用）。

# 4. 请求参数

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|:---:|---|---|
| `items` | array | 是 | 至少 1 项 | 商品项列表 |
| `items[].sku_id` | int | 是 | 必须存在且 `ACTIVE` | 目标 SKU |
| `items[].quantity` | int | 否 | 默认 1；≥ 1；≤ SKU 库存 | 购买数量 |
| `address_id` | int | 否 | 若传则必须属于当前用户 | 预览可为空 |
| `user_coupon_id` | int | 否 | 用户券 ID，不是券模板 ID | 使用优惠券 |

请求示例：

```json
{
  "items": [{"sku_id": 5, "quantity": 2}],
  "address_id": 1,
  "user_coupon_id": null
}
```

# 5. 响应字段

HTTP 200：

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "items": [
      {
        "sku_id": 5,
        "product_id": 5,
        "name": "机械键盘",
        "spec_values": {},
        "price": 399.0,
        "quantity": 2,
        "subtotal": 798.0,
        "stock": 50
      }
    ],
    "total_amount": 798.0,
    "discount_amount": 0.0,
    "pay_amount": 798.0,
    "address": {
      "id": 1,
      "receiver_name": "张三",
      "phone": "13800138000",
      "full_address": "广东省深圳市南山区科技园路1号"
    },
    "coupon": null
  }
}
```

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `items[].name` | string | - | 商品名称（非 `product_name`） |
| `items[].spec_values` | object | - | 规格键值 |
| `items[].stock` | int | - | 当前 SKU 库存快照 |
| `total_amount` | float | ≥ 0 | 商品总金额 |
| `discount_amount` | float | ≥ 0 | 优惠金额 |
| `pay_amount` | float | ≥ 0 | 应付金额 |
| `address` | object/null | - | 地址或 null |
| `coupon` | object/null | - | 券信息或 null |

# 6. 错误码与异常

| HTTP | `message` | 触发条件 |
|---:|---|---|
| 400 | `订单商品不能为空` | `items` 为空 |
| 400 | `购买数量不能小于 1` | 数量 ≤ 0 |
| 400 | `商品规格无效` | SKU 不存在或非 `ACTIVE` |
| 400 | `商品已下架` | 商品不存在或非 `ON_SALE` |
| 409 | `商品「<名称>」库存不足` | 数量 > SKU 库存 |
| 400 | `收货地址不存在` | 地址不存在或不属于当前用户 |
| 400 | `优惠券不存在` | 用户券不存在或不属于当前用户 |
| 400 | `优惠券无效或已停用` | 券模板非 `ACTIVE` |
| 409 | `优惠券已使用` | 用户券非 `UNUSED` |
| 400 | `优惠券已过期` | 当前时间晚于 `end_time` |
| 409 | `未达优惠券门槛（满<X>可用）` | 商品总金额 < 门槛 |
| 400 | `VALIDATION_ERROR` | 字段缺失/类型错误 |

所有 HTTP 错误的响应体格式：`{"code": "HTTP_ERROR", "message": "<message>", "data": null}`。

# 7. 幂等、重试与并发约束

- 纯查询接口，可安全重复调用。
- 不创建订单、不占券、不扣库存、不清购物车。
- 不锁定价格：两次预览之间商品改价，第二次按新价计算。

# 8. 测试数据准备

前置：登录用户、至少一个地址、目标 SKU、可选优惠券。准备步骤见 `DATA-ORDER-001`。

# 9. 结果查询与验证

- 断言 HTTP 200、`code=OK`；
- 断言 `total_amount = Σ(price × quantity)`；
- 断言 `pay_amount = max(total_amount - discount_amount, 0)`；
- 断言 `address`/`coupon` 与入参一致；
- 断言调用后订单数、库存、优惠券状态均未变化。

# 10. 来源与未决问题

## 来源

- `Minishop/backend/app/api/orders.py#L88-L113`：预览接口实现与响应组装。
- `Minishop/backend/app/api/orders.py#L29-L85`：共享校验与金额计算。
- `Minishop/backend/app/schemas/schemas.py#L134-L143`：请求模型。

## 未决问题

- 预览是否需要强制要求地址（当前不强制）？
- 是否需要在预览中返回券是否可用的原因列表？
- 是否需要返回预计运费、税费（当前没有）？

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：响应字段（items[].name 而非 product_name、address/coupon 显式为 null）与全部错误码/文案逐条一致（orders.py:29-113）；pay_amount=max(total-discount,0)（orders.py:84）属实。
- **复核备注**：无
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
