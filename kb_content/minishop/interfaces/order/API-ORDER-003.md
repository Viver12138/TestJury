---
id: API-ORDER-003
title: 订单列表与详情接口
knowledge_type: INTERFACE
project_id: minishop
module_id: order
source_type: API_SPEC
source_ref: Minishop/backend/app/api/orders.py#L173-L220; Minishop/backend/app/api/common.py#L142-L184
source_version: snapshot-2026-11-11
product_version:
  - "1.0.0"
platforms:
  - all
evidence_level: E2
status: in_review
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
  - query
  - api
related_ids:
  - REQ-ORDER-001
  - RULE-ORDER-011
  - API-ORDER-002
  - API-ORDER-004
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: changes_applied_pending_reapproval
change_reason: "2026-11-12 人工复核回写（审核结论：修改后通过）"
---

# 1. 接口用途

查询当前用户的订单列表，或查询单笔订单详情（含明细、支付、物流、售后状态）。管理员可通过详情接口查看任意订单。

# 2. 请求方式与路径

```http
GET /api/orders?status=<status>&page=1&page_size=10
GET /api/orders/{order_id}
Authorization: Bearer <JWT>
```

# 3. 身份认证与权限

- 列表：只返回 `user_id` 等于当前用户的订单。
- 详情：订单所有者或 `ADMIN`；其他用户返回 403。
- 无 token：401。

# 4. 请求参数

## 列表

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|:---:|---|---|
| `status` | string | 否 | 不校验枚举 | 按订单状态精确过滤 |
| `page` | int | 否 | ≥ 1，默认 1 | 页码 |
| `page_size` | int | 否 | 1–100，默认 10 | 每页数量 |

## 详情

| 字段 | 类型 | 必填 | 说明 |
|---|---|:---:|---|
| `order_id` | path int | 是 | 订单 ID |

# 5. 响应字段

## 列表（HTTP 200）

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "items": [
      {
        "id": 1,
        "order_no": "20261111173000123456",
        "status": "PAID",
        "status_cn": "已支付",
        "total_amount": 1197.0,
        "discount_amount": 10.0,
        "pay_amount": 1187.0,
        "receiver_name": "张三",
        "phone": "13800138000",
        "address_snapshot": {},
        "user_coupon_id": 1,
        "created_at": "2026-11-11T09:30:00",
        "paid_at": "2026-11-11T09:31:00",
        "shipped_at": null,
        "completed_at": null,
        "cancelled_at": null,
        "items": [],
        "payment_status": "SUCCESS",
        "shipment_company": "顺丰",
        "shipment_tracking_number": "SF123"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 10
  }
}
```

- `payment_status` 仅在存在支付记录时出现；
- `shipment_company` / `shipment_tracking_number` 仅在存在物流单时出现。

## 详情（HTTP 200）

在列表字段基础上，额外包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `payment` | object（仅存在支付记录时出现，缺省而非 null） | 支付单：`id`、`payment_no`、`method`、`amount`、`method_cn`、`status`、`status_cn`、`paid_at` |
| `shipment` | object（仅存在物流单时出现，缺省而非 null） | 物流单：`id`、`company`、`tracking_number`、`status`、`status_cn`、`shipped_at` |
| `refund` | object（仅存在退款记录时出现，缺省而非 null） | 售后：`id`、`status`、`status_cn`、`amount`、`reason`、`reject_reason` |

注意：`payment` 为单对象关系。SQLAlchemy 2.0.36 实测在存在 FAILED+SUCCESS 两条记录时确定性返回第一条（通常为 FAILED）并抛 `SAWarning: Multiple rows returned with uselist=False`；属已知缺陷（Q-05）。

# 6. 错误码与异常

| HTTP | `message` | 触发条件 |
|---:|---|---|
| 401 | `未登录` / `登录已过期，请重新登录` | 无/无效 token |
| 403 | `无权查看该订单` | 非所有者且非管理员 |
| 404 | `订单不存在` | 订单 ID 不存在 |
| 400 | `VALIDATION_ERROR` | 分页参数不合法（负数、page_size>100） |

# 7. 幂等、重试与并发约束

- 纯查询，可重复调用。
- 列表按 `id desc` 排序。
- 详情包含实时支付/物流/售后状态；在支付、发货、退款后应重新查询。

# 8. 测试数据准备

需要至少一笔订单。可用 `API-ORDER-002` 创建，并通过支付/发货接口推进状态。

# 9. 结果查询与验证

- 断言列表只含当前用户订单；
- 断言 `total` 与分页正确；
- 断言状态过滤只返回匹配状态；
- 断言详情包含明细与对应支付/物流/退款块；
- 用户 B 查询用户 A 订单，断言 403；
- 管理员查询用户 A 订单，断言 200。

# 10. 来源与未决问题

## 来源

- `Minishop/backend/app/api/orders.py#L173-L220`：列表、详情、权限判断、售后附加。
- `Minishop/backend/app/api/common.py#L142-L184`：订单/支付/物流序列化。

## 未决问题

- `status` 是否应校验枚举并返回 400？
- 多条支付记录时，详情应展示最新/成功支付还是固定第一条？
- 列表是否需要返回 `payment_status` 的稳定字段（当前仅存在支付记录时出现）？
- 是否需要管理员专用订单详情包含退款信息（当前管理端详情不含 `refund`）？

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：修改后通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：列表过滤/id desc 排序/payment_status 与 shipment_* 仅在有记录时出现、详情 403/404、管理端详情不含 refund 均属实；但把详情 payment/shipment/refund 描述为"object/null"，实际无记录时整个键缺省而非 null（common.py:164,175；orders.py:210-211），会导致断言 payment==null 的用例误判。
- **复核备注**：修订要求：三字段改为"仅存在对应记录时出现（缺省而非 null）"；payment 单对象问题按 Q-05 实测结论标注为确定性缺陷（恒返回第一条 FAILED 并抛 SAWarning）。
- **回写说明**：2026-11-12 已按复核意见回写；仍为 in_review，待复审后置 approved。
