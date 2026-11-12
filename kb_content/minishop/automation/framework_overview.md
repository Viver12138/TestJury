---
id: AUTO-FRAMEWORK
title: 自动化框架与现有能力
knowledge_type: AUTOMATION
project_id: minishop
module_id: null
source_type: AUTOMATION_DOC
source_ref: Minishop/e2e_test.py#L1-L180; Minishop/frontend/package.json; Minishop/backend/requirements.txt
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
- automation
- framework
- api
- ui
related_ids:
- AUTO-LOCATOR
- AUTO-LIMITATIONS
- TEST-ENV
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: delegated_review_completed
change_reason: 2026-11-12 用户授权技术复核；具体依据见 evidence/M2/delegated_content_review.json
---

# 1. 自动化框架与版本

## 1.1 现状

仓库**没有**正式自动化测试框架。现有资产只有：

| 资产 | 技术 | 说明 |
|---|---|---|
| `e2e_test.py` | Python + `requests` | 180 行，48 个 `check()`，直连 `http://127.0.0.1:8000/api` |
| 前端 | Vite + TypeScript | 无 Vitest/Jest/Playwright/Cypress |
| 后端 | FastAPI | 无 pytest 测试目录 |
| 数据库 | SQLite | 可用 `sqlite3` 直接断言 |
| CI | 无 | 无 CI 配置 |

`requests` **没有**写入 `backend/requirements.txt`，执行 `e2e_test.py` 需要额外安装。

## 1.2 现有脚本的行为

- 顺序执行：认证 → 商品 → 购物车 → 地址 → 优惠券 → 订单 → 支付 → 发货 → 收货 → 评价 → 库存边界 → 退款 → 越权；
- 每个 `check()` 打印 PASS/FAIL，最后统计通过/失败数；
- **不返回非零退出码**：即使有 FAIL，脚本仍以 0 结束，不适合直接作为 CI 门禁；
- 硬编码 base URL 和种子账号；
- 会写数据：创建用户、地址、订单、支付、退款、评价；
- 依赖种子数据的具体值（如机械键盘库存 50、运动鞋 8 个 SKU、新人券门槛 100）；
- 没有 setup/teardown、没有测试隔离、没有重试；
- 没有页面操作，纯 API 验证。

## 1.3 当前可执行性（2026-11-11 实测）

- 当前种子库（播种于 2026-09-21）中券#1「新人满100减10」已自然过期，可领券仅剩 2 张；`e2e_test.py#L80` 的“可领券>=3”不成立，`#L81` 的 `next(...)` 无默认值会抛 `StopIteration`，脚本中止，后续约 100 行断言不会执行。
- check() 断言失败后若正常执行到末尾仍以 0 退出，CI 无法感知这类失败；未捕获异常（如 StopIteration）会非零退出；执行前需重建种子库或改为动态取券，并补 `sys.exit(1)`。

# 2. 支持的客户端和协议

| 层面 | 支持 | 说明 |
|---|---|---|
| HTTP API | ✅ | JSON、Bearer JWT、标准 HTTP 方法 |
| 数据库 | ✅ | SQLite 文件可直读，适合做副作用断言 |
| Web UI | ⚠️ | 可人工或引入浏览器驱动；当前未安装/未配置 |
| 移动端 | ❌ | 无移动端 |
| 消息队列/异步任务 | ❌ | 无 |

# 3. 元素定位能力

- 前端**没有** `data-testid`、`data-test`、`id` 约定；
- 可用的稳定定位：
  - Ant Design 语义类：`.ant-btn`、`.ant-table`、`.ant-tag`、`.ant-modal`、`.ant-message`；
  - 业务 CSS 类：`.spec-tag`、`.product-card-image`、`.cart-image`、`.money`、`.text-muted`；
  - 文本/占位符：`用户名`、`密码`、`登 录`、`加入购物车`、`立即购买`、`提交订单`、`去支付`、`模拟支付成功`；
  - 路由 URL。
- 详见 `AUTO-LOCATOR`。

# 4. 数据准备能力

| 能力 | 支持 | 方式 |
|---|---|---|
| 创建用户 | ✅ | `POST /api/auth/register` |
| 登录 | ✅ | `POST /api/auth/login` |
| 创建地址 | ✅ | `POST /api/addresses` |
| 查询商品/SKU | ✅ | `GET /api/products` |
| 加购 | ✅ | `POST /api/cart/items` |
| 领券 | ✅ | `POST /api/coupons/{id}/claim` |
| 建券 | ✅ | `POST /api/admin/coupons`（管理员） |
| 调整库存 | ✅ | `POST /api/admin/inventory/adjust`（管理员） |
| 重置数据库 | ❌ | 只能停服删库/换库 |
| 删除订单/用户 | ❌ | 无接口 |
| 控制服务器时间 | ❌ | 无时钟注入 |

# 5. 状态读取与断言能力

- API 响应：状态码、`code`、`message`、`data` 任意字段；
- 数据库：订单、明细、支付、物流、券、库存、日志、消息；
- 页面：文本、组件状态、URL、按钮可用性；
- 缺少：内置断言库、Schema 校验、快照、报告；
- 建议断言层次见 `AUTO-LOCATOR`。

# 6. 异步、并发与等待能力

- API 为同步请求-响应，无异步任务；
- 前端有 React 异步加载与 AntD 动画，UI 自动化需等待网络响应/元素可见；
- SQLite 单写者，高并发场景会串行化；
- 没有消息队列、轮询任务、定时任务；
- 现有 `e2e_test.py` 没有显式等待/重试。

# 7. 不支持或不稳定的场景

- 真实支付/物流/短信/邮件；
- 多用户并发下单的精确时序；
- 服务器时间相关场景（券过期、订单超时）；
- 跨浏览器/移动端；
- 文件上传（商品图是数据 URL，无上传接口）；
- 真实网络故障注入。

# 8. 环境与权限限制

- 需要后端 8000 与（UI 时）前端 3000 可达；
- 管理员操作需要 `admin` token；
- 数据隔离需自行换库/换用户；
- Docker 环境当前构建失败；
- 无 CI 凭据与环境变量管理；
- `SECRET_KEY` 为开发默认值，不适合生产。

# 9. 相关示例

## 9.1 启动与执行

```powershell
# 后端（独立库）
cd Minishop\backend
$env:DATABASE_URL='sqlite:///./verify.db'
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 另一个终端
cd Minishop
python e2e_test.py
```

## 9.2 建议的框架演进（未实现）

1. 用 `pytest` + `requests` 重写 `e2e_test.py`，拆 fixtures（token、地址、SKU、券）；
2. 增加 `pytest-html`/Allure 报告与失败退出码；
3. 数据层用 SQLite fixture 或独立 `DATABASE_URL`；
4. UI 层引入 Playwright，先覆盖登录、加购、下单、支付主链路；
5. 将知识库 `RULE-*` 映射为测试标记，形成可追溯矩阵。

以上为建议，不代表仓库已具备。


# 本次授权技术复核适用性

核对 e2e_test.py：check(False) 仅计数、正常到达末尾退出 0；未捕获 StopIteration 退出非零。修正恒零描述。

本次结论基于冻结快照与既有决策，当前实现中的限制不代表目标规格；已决策但未实施的项目仍按治理台账单独跟踪。复核者为用户授权的 AI 代理，非新增人工签署。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：修改后通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：对 e2e_test.py 的描述准确（180 行、48 个 check()、纯 API 顺序执行、无非零退出码；requests 未列入 requirements.txt；前端无测试框架、后端无 pytest、无 CI、无 data-testid）。但文档把它作为"现有可用能力"登记，未说明它在当前种子库上已不可执行完毕：设计者实测 e2e_test.py:81 因新人券过期抛 StopIteration 中止，后续约 100 行断言全部不再执行；且脚本恒返回退出码 0，CI 无法感知失败。
- **复核备注**：修订要求：新增"当前可执行性"小节，写明 L80/L81 的种子时效依赖、崩溃点、以及退出码恒 0 导致不可用于 CI 门禁；修复建议为动态取券 + 断言失败时 sys.exit(1)。
- **回写说明**：2026-11-12 已按复核意见回写；仍为 in_review，待复审后置 approved。
