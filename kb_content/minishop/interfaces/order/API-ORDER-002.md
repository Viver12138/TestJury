---
id: API-ORDER-002
title: 创建订单接口
knowledge_type: INTERFACE
project_id: minishop
module_id: order
source_type: API_SPEC
source_ref: Minishop/backend/app/api/orders.py#L116-L170; Minishop/backend/app/schemas/schemas.py#L145-L149; Minishop/backend/app/api/common.py#L142-L184
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
  - create
  - api
related_ids:
  - REQ-ORDER-001
  - RULE-ORDER-006
  - API-ORDER-001
  - DATA-ORDER-001
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 接口用途

在校验通过后创建状态为 `PENDING_PAYMENT` 的订单，保存地址与商品快照，并占用所用优惠券。

# 2. 请求方式与路径

```http
POST /api/orders
Authorization: Bearer <JWT>
Content-Type: application/json
```

成功返回 **201**。

# 3. 身份认证与权限

- 必须登录；401 表示未登录/凭证失效。
- 只能使用自己的地址和用户券。
- 无角色限制。

# 4. 请求参数

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|:---:|---|---|
| `items` | array | 是 | 至少 1 项 | 商品项 |
| `items[].sku_id` | int | 是 | 存在且 `ACTIVE` | SKU |
| `items[].quantity` | int | 否 | 默认 1；≥ 1；≤ SKU 库存 | 数量 |
| `address_id` | int | 是 | 必须属于当前用户 | 收货地址 |
| `user_coupon_id` | int | 否 | 本人、未使用、未过期、达门槛 | 用户券 ID |
| `payment_method` | string | 否 | 默认 `WECHAT` | **当前未使用**，支付方式在创建支付单时决定 |

请求示例：

```json
{
  "items": [{"sku_id": 5, "quantity": 3}],
  "address_id": 1,
  "user_coupon_id": 1,
  "payment_method": "WECHAT"
}
```

# 5. 响应字段

HTTP 201：

```json
{
  "code": "OK",
  "message": "下单成功",
  "data": {
    "id": 1,
    "order_no": "20261111173000123456",
    "user_id": 2,
    "status": "PENDING_PAYMENT",
    "status_cn": "待支付",
    "total_amount": 1197.0,
    "discount_amount": 10.0,
    "pay_amount": 1187.0,
    "receiver_name": "张三",
    "phone": "13800138000",
    "address_snapshot": {
      "receiver_name": "张三",
      "phone": "13800138000",
      "province": "广东省",
      "city": "深圳市",
      "district": "南山区",
      "detail_address": "科技园路1号"
    },
    "user_coupon_id": 1,
    "created_at": "2026-11-11T09:30:00",
    "paid_at": null,
    "shipped_at": null,
    "completed_at": null,
    "cancelled_at": null,
    "items": [
      {
        "id": 1,
        "order_id": 1,
        "product_id": 5,
        "sku_id": 5,
        "product_name": "机械键盘",
        "spec_values": {},
        "price": 399.0,
        "quantity": 3,
        "subtotal": 1197.0
      }
    ]
  }
}
```

`order_no` 格式：14 位时间戳 + 6 位随机数。

# 6. 错误码与异常

与 `API-ORDER-001` 相同的校验错误，外加：

| HTTP | `message` | 触发条件 |
|---:|---|---|
| 400 | `请选择收货地址` | `address_id` 缺失或为 0 |
| 400 | `收货地址不存在` | 地址不存在或非本人 |
| 400 | `VALIDATION_ERROR` | 请求体字段缺失/类型错误 |

# 7. 幂等、重试与并发约束

- **无幂等键**：相同请求重复提交会创建多张订单。
- 使用同一张用户券重复提交：第一次成功后券变 `USED`，第二次返回 409 `优惠券已使用`。
- 不使用券的重复提交：会生成多张待支付订单。
- 创建订单不扣库存、不占库存，因此并发创建都可能成功，超卖风险在支付阶段暴露。
- 订单号唯一索引可防止完全相同的订单号，但接口未捕获唯一约束异常。

# 8. 测试数据准备

见 `DATA-ORDER-001` 第 5 节。至少需要：用户 token、地址、可用 SKU、可选用户券。

# 9. 结果查询与验证

1. 断言 HTTP 201、`code=OK`、`status=PENDING_PAYMENT`；
2. 断言金额与 `API-ORDER-001` 预览一致；
3. 断言 `address_snapshot` 字段完整；
4. 断言 `order_items` 保存商品名称、规格、单价、数量快照；
5. 断言用户券变 `USED`、`used_order_id` 指向新订单、`used_quantity+1`；
6. 断言 SKU 库存、商品销量、购物车未变化；
7. 通过 `GET /api/orders/{id}` 复核。

# 10. 来源与未决问题

## 来源

- `Minishop/backend/app/api/orders.py#L116-L170`：创建逻辑。
- `Minishop/backend/app/schemas/schemas.py#L145-L149`：请求模型。
- `Minishop/backend/app/api/common.py#L142-L184`：订单序列化字段。

## 未决问题

- `payment_method` 是否应移除或真正生效？
- 是否需要幂等键/防重复提交？
- 下单后是否应清空购物车？
- 是否应返回 201 以外的 200（保持 REST 语义）？

> 复核补充：`payment_method` 仅定义于请求 Schema，`create_order` 未使用；用例不得断言其落库（复核 2026-11-11）。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：201、响应字段、订单号 14 位时间戳+6 位随机（common.py:19-20）、地址必填 400、券置 USED 并 used_quantity+1（orders.py:162-166）、无幂等键、不扣不占库存均核实；payment_method 字段定义但未被 create_order 使用（schemas.py:149）属实。
- **复核备注**：建议标注 payment_method 为无效字段，避免用例断言其落库。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
