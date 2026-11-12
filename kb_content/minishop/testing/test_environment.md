---
id: TEST-ENV
title: MiniShop 测试环境说明
knowledge_type: TEST_SPEC
project_id: minishop
module_id: null
source_type: TEST_STANDARD
source_ref: Minishop/README.md#L16-L37; Minishop/README.md#L108-L122; Minishop/docker-compose.yml#L1-L22;
  Minishop/backend/app/config.py#L1-L23
source_version: snapshot-2026-11-11
product_version:
- 1.0.0
platforms:
- all
evidence_level: E3
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
- environment
- test_env
- local
related_ids:
- PROJECT-ENVIRONMENTS
- TEST-SPEC-PROJECT-001
- TEST-DATA
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: delegated_review_completed
change_reason: 2026-11-12 用户授权技术复核；具体依据见 evidence/M2/delegated_content_review.json
---

# 1. 环境清单

| 环境 | 状态 | 用途 |
|---|---|---|
| 本地开发（Windows） | ✅ 2026-11-11 已验证 | API/UI 调试、自动化执行 |
| Docker Compose | ❌ 构建受阻 | 类生产部署演示 |
| 测试/预发/生产 | 不存在 | - |

# 2. 本地环境

## 2.1 组件与端口

| 组件 | 地址 | 说明 |
|---|---|---|
| 前端 Vite | `http://127.0.0.1:3000` | `/api` 代理到 8000 |
| 后端 API | `http://127.0.0.1:8000` | FastAPI |
| Swagger | `http://127.0.0.1:8000/docs` | 冻结源码无环境门控，默认始终暴露 |
| SQLite | `Minishop/data/minishop.db` | 默认库 |

## 2.2 账号

| 用户名 | 密码 | 角色 | 状态 |
|---|---|---|---|
| `user` | `123456` | `USER` | ACTIVE |
| `admin` | `admin123` | `ADMIN` | ACTIVE |

> 这是项目公开种子账号，不是真实生产凭据。

## 2.3 启动命令（已验证）

```powershell
cd Minishop

# 后端（工作目录必须是 backend）
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端（另开终端）
cd ..\frontend
npm run dev -- --host 127.0.0.1 --port 3000
```

依赖安装：

```powershell
cd Minishop
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend; npm install
```

## 2.4 环境变量

| 变量 | 默认 | 测试建议 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///<repo>/data/minishop.db` | 自动化使用独立库，如 `sqlite:///./verify.db` |
| `SECRET_KEY` | 固定开发密钥 | 测试环境不需改；不要用于生产 |
| `SEED_MEDIA_DIR` | `backend/seed_media`（实际解析路径，目录不存在） | 无业务代码消费；按 Q-13 删除 |

# 3. Docker 环境（当前不可用）

`docker compose up -d --build` 预期启动：

| 服务 | 端口 | 说明 |
|---|---|---|
| backend | 8000 | `python:3.12-slim` |
| frontend | 3000 | Node 20 构建 + Nginx |

**阻塞点**：`backend/Dockerfile#L11` 执行 `COPY seed_media ./seed_media`，但 `Minishop/backend/seed_media` 不存在，构建上下文为 `./backend`，因此构建失败。`docker-compose.yml#L9` 又挂载 `./backend/seed_media`，路径同样不存在。

在修复前：

- 不要用 Docker 环境执行用例；
- 环境类失败应登记为“环境阻塞”，不是产品缺陷；
- 已确认（2026-11-11，Q-13）：删除 `Dockerfile#L11` COPY、`docker-compose.yml#L9` 挂载与 `SEED_MEDIA_DIR` 环境变量、`config.py#L15`；修复前容器环境不得作为正式测试环境。

# 4. 数据库与重置

- 默认库：`Minishop/data/minishop.db`，首次启动自动建表 + 播种。
- 独立库：在 `backend/` 目录设置 `DATABASE_URL=sqlite:///./verify.db` 后启动，验证完删除该文件。
- 重置共享库：停止后端 → 删除 `data/minishop.db` → 重启。
- 重置会清空订单/支付/退款/评价/消息/购物车/地址/收藏，并重新生成种子账号、商品、SKU、券。

# 5. 可观察性

| 对象 | 方式 |
|---|---|
| API 响应 | HTTP 状态码 + `code` + `message` + `data` |
| 订单状态 | `GET /api/orders/{id}` 或 SQL |
| 库存/销量 | `GET /api/products/{id}` 或 SQL |
| 券状态 | `GET /api/coupons/my` 或 SQL |
| 消息 | `GET /api/messages` |
| 后端日志 | uvicorn 标准输出 |
| 前端错误 | 浏览器控制台、Vite 终端 |

无 `/health` 接口；可用 `GET /` 返回固定 JSON 作为存活检查。Swagger `/docs` 无环境门控，所有环境均暴露（main.py#L11-L15）。

# 6. 已知环境问题

| 问题 | 影响 | 处理 |
|---|---|---|
| Docker 构建缺 `backend/seed_media` | 容器环境不可用 | 记录为环境缺口 |
| `.venv` 可能来自其他机器（本工作区原 venv 指向不存在的 Python 3.14） | 本地启动失败 | 用本机 Python 重建 venv |
| pip 不走系统代理时可能卡住 | 依赖安装失败 | 显式设置 `HTTPS_PROXY` 或使用可用镜像 |
| 商品图 SVG 非法 | 图片裂图 | 不作为 UI 断言点 |
| 单规格商品详情页无法加购 | UI 主流程受阻 | 用多规格商品或 API 准备数据 |
| 券有效期依赖播种日期 | 可领券集合漂移 | 动态查询券状态 |
| SQLite 单文件 | 并发写能力有限 | 并发用例单独隔离、串行复核 |

# 7. 环境验收

- 后端启动日志出现 `Application startup complete`；
- `GET /` 返回 `code=OK`；
- `GET /api/products` 返回 9 条种子商品；
- 前端 3000 返回 HTML，`/api/products` 经代理返回 200；
- 使用 `user/123456` 登录成功；
- 使用 `admin/admin123` 登录并能访问 `/api/admin/dashboard`。


# 本次授权技术复核适用性

核对配置与启动命令；Swagger 未配置环境门控。历史种子库与独立测试库必须区分。

本次结论基于冻结快照与既有决策，当前实现中的限制不代表目标规格；已决策但未实施的项目仍按治理台账单独跟踪。复核者为用户授权的 AI 代理，非新增人工签署。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：修改后通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：SEED_MEDIA_DIR 默认值写作 backend/../seed_media，代码实际解析为 Minishop/backend/seed_media（config.py:15，该目录不存在）；/docs 无环境门控，"仅开发环境暴露"表述不实（main.py:11-15）。Docker 构建必失败的判断实测正确（Dockerfile:11 + docker-compose.yml:9）；账号/端口/9 条种子商品均无误。
- **复核备注**：修订要求：SEED_MEDIA_DIR 默认路径改为 backend/seed_media；Swagger 改为"无环境门控，所有环境均暴露"；按 Q-13 决策把 seed_media 处理从未决改为"删除 COPY/挂载/环境变量/config.py:15"。
- **回写说明**：2026-11-12 已按复核意见回写；仍为 in_review，待复审后置 approved。
