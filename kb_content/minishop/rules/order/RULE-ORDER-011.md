---
id: RULE-ORDER-011
title: 订单数据的访问控制与越权边界
knowledge_type: BUSINESS_RULE
project_id: minishop
module_id: order
source_type: OTHER
source_ref: Minishop/backend/app/api/orders.py#L173-L260; Minishop/backend/app/api/admin.py#L114-L178; Minishop/backend/app/auth/dependencies.py#L13-L58
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
  - authz
  - ownership
  - "403"
  - "404"
related_ids:
  - PROJECT-ROLES
  - REQ-ORDER-001
  - API-ORDER-003
  - API-ORDER-004
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 规则陈述

普通用户只能查看和操作自己的订单；管理员可以查看任意订单并发货。不同接口对越权的响应不一致：订单详情返回 403，取消/确认收货返回 404，管理接口对普通用户返回 403。

# 2. 适用范围

- `GET /api/orders`
- `GET /api/orders/{order_id}`
- `POST /api/orders/{order_id}/cancel`
- `POST /api/orders/{order_id}/confirm`
- `GET /api/admin/orders`
- `POST /api/admin/orders/{order_id}/ship`
- 产品版本 `1.0.0`

# 3. 前置条件

- 请求已通过登录鉴权；
- 目标订单存在（管理接口）。

# 4. 触发条件

用户访问订单列表、订单详情、取消、确认收货、管理端订单或发货接口。

# 5. 规则结果

| 接口 | 访问者 | 结果 |
|---|---|---|
| `GET /api/orders` | 任意登录用户 | 只返回 `user_id` 等于自己的订单 |
| `GET /api/orders/{id}` | 订单所有者 | 200 |
| `GET /api/orders/{id}` | 管理员 | 200 |
| `GET /api/orders/{id}` | 其他用户 | 403 `无权查看该订单` |
| `POST /api/orders/{id}/cancel` | 订单所有者 | 走取消逻辑 |
| `POST /api/orders/{id}/cancel` | 其他用户 | 404 `订单不存在` |
| `POST /api/orders/{id}/confirm` | 订单所有者 | 走确认逻辑 |
| `POST /api/orders/{id}/confirm` | 其他用户 | 404 `订单不存在` |
| `GET /api/admin/orders` | 管理员 | 返回所有用户订单，可带 `username` 过滤 |
| `GET /api/admin/orders` | 普通用户 | 403 `需要管理员权限` |
| `POST /api/admin/orders/{id}/ship` | 普通用户 | 403 `需要管理员权限` |

# 6. 边界与例外

- 订单列表接口不校验查询参数 `status` 的合法性，非法值返回空列表。
- 管理端订单列表支持 `status`、`order_no` 模糊、`username` 模糊过滤；分页默认 10，最大 100。
- 管理员也可以调用普通用户的订单详情接口查看他人订单。
- 用户被禁用后，已有 token 在下次请求时返回 403 `账号已被禁用`。
- 403 与 404 的混用是当前实现事实，不是笔误；测试预期必须按接口区分。

# 7. 反例或禁止行为

- 禁止普通用户通过修改 URL 中的订单 ID 查看他人订单。
- 禁止普通用户调用 `/api/admin/**`。
- 禁止把“列表为空”误判为“没有权限”。
- 禁止在未登录时访问订单接口（应为 401，不是 403）。

# 8. 验证方式

1. 用户 A 创建订单，用户 B 用 A 的订单 ID 调用详情，预期 403。
2. 用户 B 调用取消/确认，预期 404。
3. 用户 B 调用 `/api/admin/orders`，预期 403。
4. 管理员调用详情，预期 200。
5. 无 token 调用任意订单接口，预期 401。
6. 禁用用户后使用旧 token，预期 403。

# 9. 来源依据

- `Minishop/backend/app/api/orders.py#L173-L260`：列表过滤、详情 403、取消/确认 404。
- `Minishop/backend/app/api/admin.py#L114-L178`：管理端订单列表与发货权限。
- `Minishop/backend/app/auth/dependencies.py#L13-L58`：401/403 的产生位置。

# 10. 未决问题

- 是否应统一越权语义（全 404 防枚举，或全 403 明确拒绝）？
- 管理员查看用户订单是否应记录操作日志？（`operation_logs` 表存在但未使用）

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：越权矩阵（详情 403「无权查看该订单」，取消/确认 404，管理端 403）、列表不校验非法 status 返回空、分页默认 10 上限 100、管理员可查看他人订单详情、禁用账号 403、未登录 401 均与 orders.py:181-183,206-207,226-227,250-251、admin.py:119-132、dependencies.py:17-18,32-33,56-57 一致；operation_logs 表定义但未使用属实（models.py:317）。
- **复核备注**：无
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
