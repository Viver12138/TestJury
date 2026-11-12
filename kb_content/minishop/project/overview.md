---
id: PROJECT-OVERVIEW
title: MiniShop 项目概览
knowledge_type: PROJECT
project_id: minishop
module_id: null
source_type: OTHER
source_ref: Minishop/README.md#L1-L158; Minishop/backend/app/main.py#L11-L15
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
- overview
- ecommerce
- sut
related_ids:
- PROJECT-MODULES
- PROJECT-VERSIONS
- PROJECT-ROLES
- TEST-ENV
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: delegated_review_completed
change_reason: 2026-11-12 用户授权技术复核；具体依据见 evidence/M2/delegated_content_review.json
---

# 1. 产品定位

MiniShop 是一个轻量级综合电商平台 Demo，作为 WHartTest 测试平台的真实被测系统（SUT）（README.md#L3、main.py#L13）；仓库中没有 TestJury 相关来源。它不追求商业完备性，而是提供一条可完整走通的电商交易链路，用于功能演示、自动化执行和测试用例评审。

# 2. 目标用户与角色

| 角色 | 说明 | 主要操作 |
|---|---|---|
| 匿名访客 | 未登录用户 | 浏览商品、分类、评价，注册、登录 |
| 普通用户 `USER` | 已登录消费者 | 购物车、地址、优惠券、下单、支付、取消、确认收货、退款、评价、消息、收藏 |
| 管理员 `ADMIN` | 平台运营 | 管理后台 Dashboard、用户启停、商品/分类/优惠券维护、库存调整、订单发货、退款审核、评价删除 |

详细权限见 `PROJECT-ROLES`（`project/roles_and_permissions.md`）。

# 3. 产品范围

- 用户端：注册登录、首页、商品列表/详情、购物车、地址、领券、下单、模拟支付、订单列表/详情、取消、确认收货、退款申请、评价、消息、收藏。
- 管理端：统计面板、用户管理、商品与分类管理、库存管理、订单查询与发货、优惠券管理、退款审核、评价管理。
- 技术形态：React 单页应用 + FastAPI HTTP API + SQLite。

# 4. 不在范围内的内容

以下能力当前**没有实现**，评审时不得按通用电商常识假设其存在：

- 真实支付渠道、支付回调、对账、部分支付；
- 库存预占/锁定、下单超时自动关闭、订单幂等键；
- 多商家、多仓、拆单、合并支付；
- 真实物流接口、部分发货、自动确认收货；
- 优惠券叠加、跨店券、积分、会员价；
- 发票、退货物流、换货；当前退款为“仅退款”语义（无退货/换货环节，refunds.py#L28-L38）；
- 消息推送（短信/邮件/IM）、站内信实时推送；
- 搜索引擎、推荐、移动端适配、国际化；
- 性能、容量、高可用、安全加固等非功能规格。

# 5. 当前版本

产品版本 `1.0.0`，见 `PROJECT-VERSIONS`。当前知识快照日期为 2026-11-11。

# 6. 支持平台

- Web：React 18 + Vite + Ant Design 5，面向桌面浏览器；
- API：HTTP/JSON，Swagger 文档位于 `/docs`；
- 无原生 App、小程序、桌面客户端。

详见 `PROJECT-PLATFORMS`。

# 7. 模块清单

模块清单是 `module_id` 的唯一来源，见 `project/modules.yaml`。本批试点模块为 `order`。

# 8. 关键系统依赖

| 依赖 | 用途 | 约束 |
|---|---|---|
| FastAPI | HTTP API、参数校验、Swagger | 版本见 `backend/requirements.txt` |
| SQLAlchemy | ORM 与 SQLite 访问 | 单库、无迁移工具 |
| SQLite | 业务数据存储 | 单文件 `data/minishop.db`，无并发写优化 |
| python-jose + bcrypt | JWT 签发/校验、密码哈希 | HS256、24 小时有效期 |
| React + Ant Design | 前台与后台页面 | 单页应用，`/admin` 复用同一构建 |
| Nginx / Docker Compose | 生产式部署编排 | 见 `PROJECT-ENVIRONMENTS`，当前存在构建缺口 |

# 9. 环境差异

- 本地开发：前端 3000 通过 Vite 代理 `/api` 到后端 8000；
- Docker：前端 Nginx 3000 反代 `backend:8000`；
- 两者都使用同一套 API 与种子数据，差异主要在端口、静态资源服务和数据库路径。

详见 `PROJECT-ENVIRONMENTS`。

# 10. 相关资料

- 项目说明：`Minishop/README.md`
- API：`http://127.0.0.1:8000/docs`（运行后）
- 端到端脚本：`Minishop/e2e_test.py`
- README.md#L124-L154 目录树与实际不符（components/、router/、database/ 不存在；路由在 App.tsx#L63-L101，数据库为 database.py 文件），引用路径以代码为准。
- 本知识库入口：`kb_content/minishop/README.md`


# 本次授权技术复核适用性

核对 README 与 main.py 原始定位；仅退款已实现，不把 TestJury 接入宣称成原始产品需求。

本次结论基于冻结快照与既有决策，当前实现中的限制不代表目标规格；已决策但未实施的项目仍按治理台账单独跟踪。复核者为用户授权的 AI 代理，非新增人工签署。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：修改后通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：两处失真：①overview.md:40 称服务对象为 WHartTest/TestJury，仓库仅能找到 WHartTest（README.md:3、main.py:13），TestJury 无来源；②overview.md:67 把"仅退款"列为未实现，但 refunds.py:28-38 与 Refund 模型（models.py:249-261）无退货环节，当前实现即仅退款语义。
- **复核备注**：另需加注：README.md:126-153 目录树失真（components/、router/、database/ 实测不存在，路由在 App.tsx:63-101、数据库为 database.py 文件）。README 是偏差最大的源头，凡以 README 为 source_ref 的文档都应改引代码行号。
- **回写说明**：2026-11-12 已按复核意见回写；仍为 in_review，待复审后置 approved。
