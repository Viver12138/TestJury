---
id: PROJECT-PLATFORMS
title: MiniShop 支持平台与测试入口
knowledge_type: PROJECT
project_id: minishop
module_id: null
source_type: OTHER
source_ref: Minishop/frontend/vite.config.ts#L5-L17; Minishop/frontend/src/App.tsx#L63-L101; Minishop/backend/app/main.py#L11-L15
source_version: snapshot-2026-11-11
product_version:
  - "1.0.0"
platforms:
  - web
  - api
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
  - platform
  - web
  - api
related_ids:
  - PROJECT-OVERVIEW
  - AUTO-FRAMEWORK
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: changes_applied_pending_reapproval
change_reason: "2026-11-12 人工复核回写（审核结论：修改后通过）"
---

# 1. 平台清单

| 平台 | 形态 | 入口 | 说明 |
|---|---|---|---|
| Web 前台 | React SPA | `/` | 商品、购物车、订单、用户中心 |
| Web 管理后台 | 同一 SPA 的 `/admin` 路由 | `/admin` | 需 `ADMIN` 角色 |
| HTTP API | FastAPI + JSON | `http://<host>:8000/api` | 前台与后台共用 |
| Swagger | OpenAPI UI | `http://<host>:8000/docs` | 无环境门控，所有环境均暴露（main.py#L11-L15） |

不支持：原生 App、微信小程序、桌面客户端、移动端专用布局。

# 2. Web 平台约束

- 浏览器：现代 Chromium / Firefox / Safari，需支持 ES2020 与原生 ES Module。
- 视口：页面按桌面宽度设计（Ant Design 栅格、`span` 布局），未做移动端适配。
- 路由：`BrowserRouter`，刷新任意前端路由需要服务器回退到 `index.html`；Nginx 配置已提供该回退。
- 管理后台与前台使用同一构建产物，仅通过路由与角色守卫区分。
- 前端请求基址为 `/api`，依赖同源代理；本地由 Vite 代理到 `http://localhost:8000`。

# 3. API 平台约束

- 协议：HTTP/1.1，JSON 请求与响应。
- 认证：`Authorization: Bearer <JWT>`；JWT 为 HS256，默认 24 小时有效。
- 统一响应包络：`{"code": "...", "message": "...", "data": ...}`。
- 时间字段：服务端使用 UTC naive 时间，ISO 8601 字符串返回，不带时区后缀。
- 金额字段：`float`，不是定点小数。
- 分页：`page` 从 1 开始；订单与商品的 `page_size` 上限均为 100，仅默认值不同（订单 10、商品 12）。

# 4. 可观察性入口

| 观察对象 | 方式 |
|---|---|
| 接口结果 | HTTP 状态码 + `code` + `message` + `data` |
| 订单/支付/物流状态 | `GET /api/orders/{id}`，或 `data/minishop.db` 直查 |
| 库存与销量 | `GET /api/products/{id}` 的 `stock`、`sales` |
| 优惠券状态 | `GET /api/coupons/my` |
| 消息 | `GET /api/messages` |
| 页面状态 | 页面文本、Ant Design 组件状态、URL |
| 服务日志 | uvicorn 标准输出（见 `TEST-ENV`） |

# 5. 平台差异

- 本地开发：前端 3000 由 Vite 提供并代理 `/api`；后端 8000 直接暴露。
- Docker：前端 3000 由 Nginx 提供，`/api/` 反代到 `backend:8000`；但 compose 仍将 8000 发布到宿主机（docker-compose.yml#L5-L6），后端直接可达。
- 两种方式的 API 行为一致，差异只在网络路径与静态资源缓存。

# 6. 自动化适用性

- API 自动化：推荐，覆盖全部业务规则与状态转换。
- UI 自动化：可行但存在已知障碍（无 `data-testid`、单规格商品无法加购、商品图损坏），详见 `AUTO-LIMITATIONS`。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：修改后通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：platforms.md:44 称 Swagger"仅开发/测试环境暴露"，实际 main.py:11-15 无环境开关、/docs 恒开，且 docker-compose.yml:5-6 把 8000 直接发布到宿主机，与其:80"后端不直接暴露给浏览器"自相矛盾；:63 称 page_size 上限因模块而异，实测订单与商品上限均为 100（orders.py:177、products.py:64），仅默认值不同（10/12）。
- **复核备注**：其余（角色守卫 App.tsx:50-61、nginx 回退、vite 代理、无 data-testid、单规格无法加购、商品图 data URL 含 '#' 损坏）已核实无误。
- **回写说明**：2026-11-12 已按复核意见回写；仍为 in_review，待复审后置 approved。
