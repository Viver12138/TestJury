# 阶段一交付：MiniShop 项目资料盘点

> 项目：`minishop`
> 盘点日期：2026-11-11
> 机读清单：`kb_content/_delivery/source_inventory.yaml`（80 条，含 SHA-256、行数、分类）
> 原则：只登记真实存在、可打开、可核对的资料；不把依赖目录、构建产物、运行日志当作项目资料。

## 1. 盘点范围与方法

### 1.1 扫描范围

- 项目根：`Minishop/`
- 扫描内容：全部受项目维护的源码、说明、测试脚本、部署配置、数据库快照。
- 排除内容：`node_modules/`、`.venv/`、`frontend/dist/`、`__pycache__/`、`*.pyc`、`*.tsbuildinfo`、运行日志、`pip-*` 临时目录。
- 运行态核对：读取本机已启动的 `http://127.0.0.1:8000/openapi.json`，与代码路由交叉核对。
- 数据核对：用 SQLite 只读查询 `data/minishop.db` 的表、索引和种子数据。

### 1.2 盘点方法

1. 文件系统遍历 + 计算行数/字节/SHA-256；
2. 后端按 `APIRouter` 与 OpenAPI 操作清单核对；
3. 前端按 `App.tsx` 路由与页面文件核对；
4. 数据库按 `models.py` 与 `sqlite_master` 双向核对；
5. 文档声明与实现逐条比对，冲突进入潜在冲突清单。

## 2. 项目资料清单

### 2.1 总量

| 类别 | 文件数 | 行数/说明 |
|---|---:|---|
| 项目说明文档 | 1 | `README.md`，158 行 |
| 后端源码 | 28 | 2,345 行 |
| 前端源码 | 35 | 33 个 TS/TSX 源文件（2,619 行）+ CSS + `index.html` |
| 测试脚本 | 1 | `e2e_test.py`，180 行，48 个 `check()` |
| 部署/配置 | 14 | Dockerfile、Compose、Nginx、依赖与 TS/Vite 配置 |
| 数据快照 | 1 | `data/minishop.db`，200,704 字节 |
| **合计** | **80** | 9,450 行文本（不含二进制库） |

### 2.2 文档类

| 资料 | 定位 | 内容 | 可用于 |
|---|---|---|---|
| 项目 README | `Minishop/README.md#L1-L158` | 定位、技术栈、启动方式、账号、功能清单、数据模型、状态枚举、种子数据、已实现业务规则 | 项目/需求/规则/流程的**意图**，不是经审批的正式规格 |
| 知识库规范 | `C:\Users\Viver\Desktop\TestJury_项目知识库数据规范_v1.0.md`（项目外部） | 本次交付的格式与治理依据 | 元数据、结构、证据等级、缺口/冲突规范 |

仓库内**没有**：PRD、需求规格说明书、设计文档、接口文档正文、数据库设计文档、测试计划、测试用例、缺陷记录、会议纪要、发布说明。

### 2.3 后端源码类

| 分组 | 文件 | 行数量级 | 主要知识 |
|---|---|---:|---|
| 应用入口 | `app/main.py` | 79 | 路由注册、统一错误格式、启动播种 |
| 配置/数据库 | `app/config.py`、`app/database.py` | 61 | 端口外配置、SQLite 连接、建表 |
| 数据模型 | `app/models/models.py` | 326 | 18 张表、字段、索引、状态枚举 |
| 请求 Schema | `app/schemas/schemas.py` | 192 | 入参字段、必填、长度、数值范围 |
| 认证授权 | `app/auth/security.py`、`app/auth/dependencies.py` | 98 | bcrypt、JWT、当前用户、管理员校验 |
| 种子数据 | `app/seed/seed.py` | 162 | 2 账号、4 分类、9 商品、16 SKU、4 券 |
| 业务路由 | `app/api/{auth,products,cart,addresses,favorites,coupons,orders,payments,refunds,reviews,messages,admin,common}.py` | 约 1,400 | 68 个 API 的实际行为、状态码、错误消息 |
| 空占位 | `app/services/__init__.py`、各 `__init__.py` | 0 | 无业务逻辑 |

### 2.4 前端源码类

| 分组 | 文件 | 主要知识 |
|---|---|---|
| 路由与入口 | `src/App.tsx`、`src/main.tsx` | 26 条路由、登录/管理员守卫、懒加载 |
| 布局 | `src/layouts/MainLayout.tsx`、`AdminLayout.tsx` | 前台/后台导航、购物车与未读角标 |
| 商城页面 | `pages/home`、`pages/product`、`pages/cart`、`pages/order`、`pages/payment` | 浏览、详情、加购、结算、模拟支付 |
| 用户中心 | `pages/user/*` | 订单、地址、收藏、券、评价、售后、消息 |
| 管理后台 | `pages/admin/*` | Dashboard、用户、商品、分类、库存、订单、券、退款、评价 |
| 基础设施 | `src/api/client.ts`、`src/api/index.ts`、`src/store/auth.tsx`、`src/types/index.ts` | Axios 拦截器、请求封装、登录态、类型 |

前端**没有**自动化测试、组件测试、Storybook、`data-testid`；全仓库 `data-testid` 计数为 0。

### 2.5 测试类

| 资料 | 定位 | 内容 | 性质 |
|---|---|---|---|
| 端到端脚本 | `Minishop/e2e_test.py#L1-L180` | `requests` 直连 8000，48 个断言，覆盖登录/商品/购物车/地址/优惠券/订单/支付/发货/收货/评价/退款/越权 | **可执行行为证据**，不是测试规范或测试用例库 |

- 没有 pytest/unittest 测试文件；
- 没有页面对象、测试数据工厂、断言库；
- 脚本硬编码 `http://127.0.0.1:8000/api`，会修改数据库（创建订单、用户、评价等）；
- 2026-11-11 在临时库上执行结果：**48 通过 / 0 失败**。

### 2.6 部署与配置类

| 资料 | 定位 | 关键事实 |
|---|---|---|
| 后端依赖 | `backend/requirements.txt` | 9 个固定版本依赖 |
| 后端镜像 | `backend/Dockerfile` | `python:3.12-slim`；第 11 行 `COPY seed_media` |
| 前端依赖 | `frontend/package.json`、`package-lock.json` | React 18、Vite 6、AntD 5、TS 5.6 |
| 前端镜像 | `frontend/Dockerfile` | Node 20 构建 + Nginx |
| Compose | `docker-compose.yml` | backend 8000、frontend 3000、`./data` 与 `./backend/seed_media` 挂载 |
| Nginx | `frontend/nginx.conf`、`nginx/nginx.conf` | SPA 回退、`/api/` 反代、静态缓存 |
| 前端构建 | `vite.config.ts`、`tsconfig*.json` | 3000 端口、`/api` 代理到 8000 |
| 忽略规则 | `.gitignore`、`.dockerignore` | 依赖、构建产物、数据库、日志被忽略 |

### 2.7 数据类

`data/minishop.db`（SQLite）：

| 指标 | 值 |
|---|---:|
| 表 | 18 |
| 显式索引 | 24 |
| 用户 | 2（admin、user） |
| 分类 | 4 |
| 商品 | 9 |
| SKU | 16（运动鞋 8 个规格） |
| 优惠券模板 | 4（3 个 ACTIVE，1 个 DISABLED/已过期） |
| 订单/支付/退款/评价/消息/收藏/购物车/地址 | 均为 0（干净种子库） |

### 2.8 运行态契约

`GET /openapi.json` 当前包含：

- 69 个 operation（68 个 `/api/**` + 1 个 `GET /`）；
- 13 个 tag：认证、商品、购物车、地址、收藏、优惠券、订单、支付、售后、评价、消息、管理后台、根；
- 未提供 `operationId` 以外的外部 API 文档。

## 3. 资料分类结果

按 TestJury 知识类型归类：

| 知识类型 | 可用来源 | 充分性 |
|---|---|---|
| `PROJECT` | README、`main.py`、`models.py`、`App.tsx`、Compose、package/requirements | 足以整理项目级概览，但无正式立项材料 |
| `REQUIREMENT` | README 功能清单 + API 实现 | 只有**实现反推需求**，无正式 PRD/验收标准 |
| `BUSINESS_RULE` | README “核心业务规则” + `api/*.py` | 交易域规则可逐条定位；非交易模块未完整提取 |
| `WORKFLOW` | README 流程描述 + 代码状态字段 | 可重建订单主流程与状态机；无流程图/设计文档 |
| `INTERFACE` | FastAPI 路由、Pydantic Schema、OpenAPI、SQLite 表结构 | 接口契约充分；无独立 API 文档 |
| `TEST_SPEC` | 无项目测试规范；`e2e_test.py` 只体现少量约定 | **缺失**，需项目方补充或引用全局规范 |
| `AUTOMATION` | `e2e_test.py`、`package.json`、运行环境 | 只能说明“有一个 requests 脚本”，无框架化能力 |
| `GLOSSARY` | README 术语、代码枚举 | 可整理，但无项目术语表 |
| `HISTORICAL_BUG` | 无缺陷系统、无 Git 历史 | **缺失** |
| `EXPERT_KNOWLEDGE` | 本次代码走查发现的风险 | 只能作为 E4 线索，不能当业务事实 |

## 4. 资料完整性分析

### 4.1 项目级（规范 16.1）

| 检查项 | 状态 | 说明 |
|---|:---:|---|
| 项目概览与产品定位 | ⚠️ | README 有定位，但无正式项目立项/范围说明；已整理为候选 |
| 当前产品版本 | ✅ | 代码与 package.json 均为 1.0.0 |
| 支持平台 | ⚠️ | Web/API 可从代码确认；无浏览器兼容性声明 |
| 模块清单 | ⚠️ | 由路由和页面反推，无官方模块划分 |
| 用户角色与权限 | ✅ | 代码可完整核对（匿名/USER/ADMIN） |
| 测试环境说明 | ✅ | 本机已实际启动验证；Docker 存在构建缺口 |

### 4.2 模块级（规范 16.2，试点 `order`）

| 检查项 | 状态 | 说明 |
|---|:---:|---|
| 正式需求或功能规格 | ❌ | 无 PRD；现有 REQ 为“代码 + README”整理稿 |
| 核心业务规则 | ⚠️ | 11 条规则可从代码逐条定位，但未经业务确认 |
| 主流程 | ⚠️ | 可从页面与接口重建，无正式流程文档 |
| 异常流程 | ⚠️ | 可从错误分支重建，无正式异常规格 |
| 关键状态及转换 | ⚠️ | 可从状态字段与赋值点重建，无正式状态机文档 |
| 接口和数据约束 | ✅ | OpenAPI + Schema + SQLite 表结构可核对 |
| 结果观察与验证方式 | ✅ | API 响应、数据库、页面状态均可观察 |
| 未决问题和知识缺口 | ✅ | 已登记 |

### 4.3 TestJury 评审准备（规范 16.3）

| 检查项 | 状态 |
|---|:---:|
| 明确 Rubric 版本 | ❌ |
| 明确评审对象与知识库范围 | ✅（本批范围已写明） |
| 真实测试用例作为输入 | ❌ |
| 人工标注检索黄金集 | ❌ |
| 人工标注评审黄金集 | ❌ |
| 知识库发布版本 | ⚠️（候选快照，未发布） |
| 检索回归 | ❌ |
| K0/K1 对照评测 | ❌ |

## 5. 缺失资料清单

| 编号 | 缺失资料 | 影响的评审维度 | 严重度 |
|---|---|---|---|
| M-01 | 正式 PRD / 需求规格 / 验收标准 | 业务意图、预期结果、规则正确性 | 高 |
| M-02 | 业务负责人确认记录 | 所有业务规则的权威性 | 高 |
| M-03 | 项目测试规范 / 测试策略 | 测试设计质量、覆盖要求 | 高 |
| M-04 | 测试用例库与评审黄金集 | 评审效果验证 | 高 |
| M-05 | 缺陷系统 / 历史缺陷 / 根因记录 | 风险线索、复发条件 | 中 |
| M-06 | Git 仓库 / 版本标签 / commit | 知识发布追溯、版本差异 | 高 |
| M-07 | 数据库迁移脚本 / Schema 版本 | 数据兼容性、升级验证 | 中 |
| M-08 | UI 设计稿 / 交互规格 / 文案规范 | 页面预期结果、UI 自动化 | 中 |
| M-09 | 接口文档正文（仅 OpenAPI 自动生成） | 字段语义、错误码目录 | 中 |
| M-10 | 非功能需求（性能、安全、可用性） | 非功能评审 | 中 |
| M-11 | 发布说明 / 变更日志 | 版本适用性判断 | 中 |
| M-12 | CI/CD 配置与质量门禁 | 自动化可行性、回归策略 | 低 |
| M-13 | 真实支付/物流等外部依赖契约 | 涉及外部系统的用例 | 低（Demo 无此能力） |

## 6. 潜在冲突清单（初步）

> 详细字段、证据与处置见 `minishop/_governance/conflicts.yaml`。此处只登记“需要人工确认”，不裁决。

| 编号 | 冲突主题 | 一方 | 另一方 | 影响 |
|---|---|---|---|---|
| C-01 | “立即购买”行为 | README 声称商品详情支持立即购买 | 前端实现为加购后跳购物车 | 购买路径用例预期 |
| C-02 | 库存安全 | README 声称下单校验库存 | 下单不占库存，支付用 `max(stock-qty,0)` 扣减，可超卖 | 并发/库存边界用例 |
| C-03 | 项目结构 | README 结构树列出 `components/`、`router/`、`database/` 目录 | 实际不存在（`database.py` 是文件） | 文档导航、自动化路径 |
| C-04 | 待发货状态 | 代码多处引用 `PENDING_SHIPMENT` | 全仓库没有任何赋值点，实际不可达 | 状态机覆盖、发货前置 |
| C-05 | Docker 构建 | Dockerfile/Compose 依赖 `backend/seed_media` | 该目录不存在，构建会在 `COPY` 失败 | 环境可用性 |
| C-06 | 优惠券发放量 | `total_quantity` 与“已领完”提示暗示发放上限 | 领券不计数，只有使用才累加 `used_quantity` | 券库存/领取边界 |
| C-07 | 支付记录基数 | 订单模型 `payment` 为单对象关系 | 支付失败后允许再建支付单，同一订单可多条支付记录 | 订单详情展示、断言 |
| C-08 | 销售额口径 | Dashboard 同时统计销售额与退款额 | 销售额把 `REFUNDED` 订单也计入，退款额另计 | 统计类用例预期 |
| C-09 | 单规格商品加购 | README 声称商品可加购 | 前端详情页对无规格商品永远无法选中 SKU | UI 主流程用例 |
| C-10 | 退款拒绝后的状态 | 状态机直觉：拒绝后回到退款前状态 | 代码统一回 `PAID`，`SHIPPED/COMPLETED` 状态丢失 | 退款/状态回归用例 |

## 7. 阶段一结论

- 资料足以支撑**交易域**候选知识库的整理，尤其是接口、状态、金额、权限和种子数据。
- 资料不足以支撑“正式评审”：缺少 PRD、测试规范、测试用例、缺陷历史、Git 追溯和业务审核。
- 所有候选知识必须保持 `in_review`，不得标记为 `approved`。
- 下一步（阶段二）优先整理 `order` 模块，并把本清单中的冲突与缺口转为治理记录。
