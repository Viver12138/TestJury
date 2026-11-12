---
id: PROJECT-ENVIRONMENTS
title: MiniShop 环境与运行方式
knowledge_type: PROJECT
project_id: minishop
module_id: null
source_type: OTHER
source_ref: Minishop/docker-compose.yml#L1-L22; Minishop/backend/Dockerfile#L1-L15;
  Minishop/frontend/vite.config.ts#L5-L17; Minishop/backend/app/config.py#L1-L23
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
- environment
- deployment
- local
- docker
related_ids:
- TEST-ENV
- PROJECT-PLATFORMS
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: delegated_review_completed
change_reason: 2026-11-12 用户授权技术复核；具体依据见 evidence/M2/delegated_content_review.json
---

# 1. 环境清单

| 环境 | 用途 | 状态 |
|---|---|---|
| 本地开发（Windows） | 日常开发、API/UI 调试、自动化执行 | 已验证可运行（2026-11-11） |
| Docker Compose | 类生产部署演示 | 编排文件存在，但存在构建缺口，见第 4 节 |
| 测试/预发/生产 | 无 | 仓库未提供 |

# 2. 本地开发环境

## 2.1 组件与端口

| 组件 | 端口 | 启动方式 |
|---|---:|---|
| 后端 FastAPI | 8000 | `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| 前端 Vite | 3000 | `npm run dev` |
| SQLite | - | 文件 `data/minishop.db`，随后端启动自动建表与播种 |

## 2.2 已验证的启动步骤（Windows / PowerShell）

```powershell
cd Minishop

# 1) 创建虚拟环境并安装后端依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 2) 启动后端（工作目录必须是 backend）
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3) 另开终端启动前端
cd ..\frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3000
```

访问：

- 前台：`http://127.0.0.1:3000`
- 管理后台：`http://127.0.0.1:3000/admin`
- API 文档：`http://127.0.0.1:8000/docs`

## 2.3 依赖版本

- 后端见 `backend/requirements.txt`（FastAPI 0.115.6、SQLAlchemy 2.0.36、pydantic 2.10.4、uvicorn 0.34.0 等）。
- 前端见 `frontend/package.json`（React 18、Vite 6、Ant Design 5、TypeScript 5.6）。
- 本机验证使用 Python 3.13.2、Node.js 24.19.0、npm 11.17.0。

# 3. 配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///<repo>/data/minishop.db` | SQLAlchemy 连接串 |
| `SECRET_KEY` | `minishop-dev-secret-key-change-in-prod` | JWT 签名密钥，生产必须替换 |
| `SEED_MEDIA_DIR` | `backend/seed_media`（相对 backend 解析，实际不存在） | 无业务代码消费；按 Q-13 决策删除该配置（config.py#L15） |

CORS 白名单固定为 `http://localhost:3000`、`http://127.0.0.1:3000`、`http://localhost:8000`、`http://127.0.0.1:8000`。

# 4. Docker Compose

`docker-compose.yml` 定义两个服务：

| 服务 | 镜像/构建 | 端口 | 数据 |
|---|---|---|---|
| `backend` | `backend/Dockerfile`，`python:3.12-slim` | `8000:8000` | `./data:/app/data` |
| `frontend` | `frontend/Dockerfile`，Node 20 构建 + Nginx | `3000:80` | 无 |

**已知构建缺口**：`backend/Dockerfile` 第 11 行执行 `COPY seed_media ./seed_media`，但 `backend/seed_media` 目录不存在，构建上下文为 `./backend`，因此 `docker compose up --build` 会在该步骤失败。`docker-compose.yml` 又挂载了 `./backend/seed_media`，与该目录位置不一致。

在修复前，Docker 部署不能作为可执行环境；评审涉及部署验证时，应登记为环境阻塞而非用例缺陷。

**已确认处理方式（2026-11-11，Q-13）**：删除 `Dockerfile#L11` 的 `COPY seed_media`、`docker-compose.yml#L9` 的 `./backend/seed_media` 挂载与 `SEED_MEDIA_DIR` 环境变量、`config.py#L15` 的配置；该目录无业务代码消费。修复前容器环境不得作为正式测试环境。

# 5. 数据目录与重置

- 数据库：`Minishop/data/minishop.db`（Docker 中为 `/app/data/minishop.db`）。
- 首次启动自动 `create_all` 并执行幂等 seed。
- 重置方式：停止后端，删除 `data/minishop.db`，重新启动；种子数据会重新生成。
- 注意：重置会清空订单、支付、退款、评价等运行数据；种子优惠券有效期会按新的播种时间计算。

# 6. 日志与诊断

- 后端日志：uvicorn 标准输出/错误输出；启动成功会打印 `MiniShop database initialized, seed data ready.`。
- 前端日志：Vite 终端输出与浏览器控制台。
- 健康检查：仓库**没有** `/health` 接口；可用 `GET /` 返回固定 JSON 作为存活探测。

# 7. 环境差异对测试的影响

| 差异 | 影响 |
|---|---|
| SQLite 单文件 | 并发写有限，订单/支付并发场景结果受执行时序影响 |
| 本地 Vite 代理 | 前端 3000 的 `/api` 转发到 `localhost:8000`，后端必须可达 |
| Docker Nginx 反代 | 静态资源缓存 30 天，前端更新后需考虑缓存 |
| 种子时间 | 优惠券有效期相对播种时间，不同环境可领券集合可能不同 |

# 8. 未决问题

- ~~`backend/seed_media` 缺失应通过补目录还是删除 `COPY` 修复~~ 已确认（2026-11-11，Q-13）：删除相关配置；仅保留“是否提供 /health、版本接口与迁移脚本”和生产安全项为未决。
- 是否需要提供 `/health`、版本接口与数据库迁移脚本；
- 生产密钥、HTTPS、反向代理安全头均未配置。


# 本次授权技术复核适用性

核对冻结 Dockerfile/compose/config 的 seed_media 缺口；历史 MiniShop 构建失败不代表 TestJury PostgreSQL 不可用。

本次结论基于冻结快照与既有决策，当前实现中的限制不代表目标规格；已决策但未实施的项目仍按治理台账单独跟踪。复核者为用户授权的 AI 代理，非新增人工签署。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：修改后通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：environments.md:133 仍把 seed_media 写成"补目录还是删 COPY"的未决问题，与本轮 Q-13 决策（删除）矛盾；:92 写 SEED_MEDIA_DIR 默认值为 backend/../seed_media，实际由 config.py:15 解析为 backend/seed_media（该目录不存在）。Docker 构建必失败于 Dockerfile:11（build context=./backend）。
- **复核备注**：§8 改为已决策口径：删除 Dockerfile:11 COPY、docker-compose.yml:9 挂载与 SEED_MEDIA_DIR 环境变量、config.py:15；修复前容器环境不得作为正式测试环境。其余端口/命令/依赖版本核实一致。
- **回写说明**：2026-11-12 已按复核意见回写；仍为 in_review，待复审后置 approved。
