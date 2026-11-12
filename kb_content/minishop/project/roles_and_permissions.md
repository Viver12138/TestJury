---
id: PROJECT-ROLES
title: 用户角色与权限
knowledge_type: PROJECT
project_id: minishop
module_id: null
source_type: OTHER
source_ref: Minishop/backend/app/auth/dependencies.py#L13-L58; Minishop/backend/app/api/orders.py#L201-L260; Minishop/backend/app/api/admin.py#L22-L334
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
  - role
  - permission
  - authz
related_ids:
  - RULE-ORDER-011
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: changes_applied_pending_reapproval
change_reason: "2026-11-12 人工复核回写（审核结论：修改后通过）"
---

# 1. 角色定义

| 角色值 | 名称 | 获取方式 |
|---|---|---|
| 匿名 | 未携带有效 token | 无需登录 |
| `USER` | 普通用户 | 注册或种子账号 `user/123456` |
| `ADMIN` | 管理员 | 种子账号 `admin/admin123`；无自助注册入口 |

角色存储在 `users.role` 字段，取值为 `USER` / `ADMIN`。

# 2. 认证机制

- 登录成功返回 JWT，payload 包含 `sub`（用户 ID 字符串）、`role`、`exp`。
- 每个受保护请求由 `get_current_user` 解析 token，并**从数据库重新加载用户**。
- 权限判断使用数据库中的 `users.role`，不使用 token 内的 `role` 声明。
- 用户被禁用（`status != ACTIVE`）后，已有 token 立即失效（返回 403）。
- token 缺失/无效/过期：401；账号禁用：403。

# 3. 权限矩阵

| 能力 | 匿名 | USER | ADMIN |
|---|:---:|:---:|:---:|
| 浏览商品/分类/评价 | ✅ | ✅ | ✅ |
| 注册、登录 | ✅ | ✅ | ✅ |
| 查看自己的信息（GET /api/auth/me） | ❌ | ✅ | ✅ |
| 购物车增删改查 | ❌ | ✅（仅自己） | ✅（仅自己） |
| 地址增删改查/默认地址 | ❌ | ✅（仅自己） | ✅（仅自己） |
| 领券、我的优惠券 | ❌ | ✅ | ✅ |
| 下单、支付、取消、确认收货 | ❌ | ✅（仅自己） | ✅（仅自己） |
| 申请退款、查看自己的售后 | ❌ | ✅（仅自己） | ✅（仅自己） |
| 评价（已完成订单） | ❌ | ✅（仅自己） | ✅（仅自己） |
| 站内消息/收藏 | ❌ | ✅（仅自己） | ✅（仅自己） |
| 查看任意订单详情 | ❌ | ❌ | ✅ |
| 管理后台全部接口（`/api/admin/**`） | ❌ | ❌（403） | ✅ |
| 禁用管理员账号 | ❌ | ❌ | ❌（400，禁止） |

> 当前没有资料修改接口（auth 模块仅 register/login/me/logout）；不要设计“修改个人信息”用例（复核 2026-11-11）。

# 4. 数据归属边界

- 购物车项、地址、优惠券、订单、退款、评价、消息、收藏均按 `user_id` 隔离。
- 订单详情：非本人且非管理员 → **403**（`无权查看该订单`）。
- 订单取消/确认收货/退款申请：查询后校验归属，非本人 → **404**（`订单不存在`），不暴露存在性。
- 管理端订单列表可查看所有用户订单；`ADMIN` 也可通过 `GET /api/orders/{id}` 查看他人订单。

这种 403/404 的不一致是当前实现事实，评审预期结果时必须按接口分别断言，不能统一假设。

# 5. 管理员保护

- `PUT /api/admin/users/{id}/status` 不允许把 `ADMIN` 账号改为非 `ACTIVE`，返回 400。
- 管理员可以禁用普通用户；被禁用用户立即无法登录和调用受保护接口。
- 管理员账号不能在页面上自助注册。

# 6. 验证方式

```http
# 普通用户访问管理接口，预期 403
GET /api/admin/dashboard
Authorization: Bearer <USER_TOKEN>

# 用户 B 查看用户 A 的订单，预期 403
GET /api/orders/<A_ORDER_ID>
Authorization: Bearer <B_TOKEN>

# 用户 B 取消用户 A 的待支付订单，预期 404
POST /api/orders/<A_ORDER_ID>/cancel
Authorization: Bearer <B_TOKEN>
```

# 7. 未决问题

- 权限变更是否需要 token 主动失效机制（当前依赖每次查库，已天然生效）。
- 是否需要更细粒度的管理员分权（当前只有单一 `ADMIN`）。
- 403/404 语义是否应统一。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：修改后通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：roles_and_permissions.md:59 权限矩阵声称 USER/ADMIN 可"修改自己的信息"，但后端 auth 模块仅有 register/login/me/logout，无任何资料修改接口（前端亦仅 api/index.ts:8 的 me()）。
- **复核备注**：改为"查看自己的信息（GET /api/auth/me）；当前无资料修改接口"，或在未决问题登记该缺口。其余 401/403 语义、越权矩阵、禁用管理员 400、/api/admin/** 全走 require_admin、注册固定 USER 均核实一致。
- **回写说明**：2026-11-12 已按复核意见回写；仍为 in_review，待复审后置 approved。
