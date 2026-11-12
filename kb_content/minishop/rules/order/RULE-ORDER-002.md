---
id: RULE-ORDER-002
title: 收货地址必须归属当前用户并写入订单快照
knowledge_type: BUSINESS_RULE
project_id: minishop
module_id: order
source_type: OTHER
source_ref: Minishop/backend/app/api/orders.py#L34-L43; Minishop/backend/app/api/orders.py#L116-L143
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
  - address
  - snapshot
  - ownership
related_ids:
  - REQ-ORDER-001
  - API-ORDER-002
  - DATA-ORDER-001
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: changes_applied_pending_reapproval
change_reason: "2026-11-12 人工复核回写（审核结论：修改后通过）"
---

# 1. 规则陈述

创建订单时 `address_id` 必填且必须属于当前登录用户；订单必须把收货人、电话和完整地址写入地址快照，后续地址修改或删除不影响已创建订单。

# 2. 适用范围

- `POST /api/orders`（创建订单，地址必填）
- `POST /api/orders/preview`（预览，地址可选；若传则必须归属当前用户）
- 产品版本 `1.0.0`

# 3. 前置条件

- 用户已登录；
- 用户已创建至少一个收货地址（创建订单时）。

# 4. 触发条件

调用创建订单接口并传入 `address_id`，或调用预览接口并传入 `address_id`。

# 5. 规则结果

- 创建订单 `address_id=0`：400 `请选择收货地址`；
- 创建订单 `address_id` 缺失、为 null 或类型非法：400 `VALIDATION_ERROR`（FastAPI 请求校验，main.py#L47-L52）。
- `address_id` 指向不存在或不属于当前用户的地址：400 `收货地址不存在`。
- 地址校验通过后，订单写入：
  - `receiver_name`、`phone`；
  - `address_snapshot`，JSON 包含 `receiver_name`、`phone`、`province`、`city`、`district`、`detail_address`。
- 预览接口在地址缺失时允许返回 `address: null`，不阻断金额预览。

# 6. 边界与例外

- 地址归属只按 `user_id` 判断，管理员下单同样只能使用自己的地址。
- 地址快照是创建订单时的值；之后修改或删除地址不会回写订单。
- 地址的默认标记不影响下单选择，前端默认选中默认地址，但 API 不做该限制。
- 地址字段没有手机号格式、长度、省市区完整性校验。

# 7. 反例或禁止行为

- 禁止使用他人地址下单。
- 禁止只保存 `address_id` 而不保存快照。
- 禁止在创建订单时允许空地址。

# 8. 验证方式

1. 不传/null `address_id` 创建订单：400 `VALIDATION_ERROR` 参数校验失败。
2. 传 `address_id=0`：400 `请选择收货地址`。
3. 用户 B 使用用户 A 的地址 ID 创建订单，预期 400。
4. 创建订单后修改地址，查询订单详情，确认地址快照不变。
5. 预览不传地址，确认仍返回金额且 `address=null`。

# 9. 来源依据

- `Minishop/backend/app/api/orders.py#L34-L43`：地址查询与归属校验。
- `Minishop/backend/app/api/orders.py#L116-L143`：创建订单时地址必填与快照写入。
- `Minishop/backend/app/api/addresses.py#L19-L75`：地址维护接口。

# 10. 未决问题

- 是否需要校验手机号与省市区完整性？
- 地址删除后是否应禁止删除被历史订单引用的地址？（当前允许，订单靠快照保留）
- 是否需要限制每用户地址数量？

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：修改后通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：§5"address_id 为空、为 0 或缺失 → 400 请选择收货地址"有误：缺失/null 返回 400 VALIDATION_ERROR（main.py:47-52；schemas.py:147），仅传 0 命中 orders.py:118-119。归属校验、地址快照字段、地址无格式校验、前端默认选中默认地址（OrderConfirm.tsx:28）均一致。
- **复核备注**：修订要求：区分"传 0 → 请选择收货地址"与"缺失/非法 → VALIDATION_ERROR"，并同步验证方式章节。
- **回写说明**：2026-11-12 已按复核意见回写；仍为 in_review，待复审后置 approved。
