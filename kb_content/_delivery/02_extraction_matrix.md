# 阶段二交付：知识提取映射

> 目的：说明每份候选知识来自哪里、覆盖了哪些规则、哪些仍是空白。
> 原则：只映射真实来源；未提取的内容登记为缺口，不用推断补齐。

## 1. 知识文件清单（37 份）

| 类型 | 数量 | ID |
|---|---:|---|
| `PROJECT` | 5 | `PROJECT-OVERVIEW`、`PROJECT-VERSIONS`、`PROJECT-PLATFORMS`、`PROJECT-ROLES`、`PROJECT-ENVIRONMENTS` |
| `REQUIREMENT` | 4 | `REQ-ORDER-001` ~ `REQ-ORDER-004` |
| `BUSINESS_RULE` | 11 | `RULE-ORDER-001` ~ `RULE-ORDER-011` |
| `WORKFLOW` | 2 | `FLOW-ORDER-001`、`STATE-ORDER-001` |
| `INTERFACE` | 7 | `API-ORDER-001` ~ `API-ORDER-006`、`DATA-ORDER-001` |
| `TEST_SPEC` | 3 | `TEST-SPEC-PROJECT-001`、`TEST-ENV`、`TEST-DATA` |
| `AUTOMATION` | 3 | `AUTO-FRAMEWORK`、`AUTO-LOCATOR`、`AUTO-LIMITATIONS` |
| `GLOSSARY` | 1 | `GLOSSARY-001` |
| `EXPERT_KNOWLEDGE` | 1 | `EXP-ORDER-001` |
| **合计** | **37** | 全部 `status=in_review` |

## 2. 来源 → 知识映射

| 来源 | 提取出的知识 | 说明 |
|---|---|---|
| `Minishop/README.md` | `PROJECT-*`、`REQ-ORDER-*`、`RULE-ORDER-*`（意图）、`FLOW-ORDER-001` | README 是唯一项目说明，但只是意图声明 |
| `backend/app/main.py` | `PROJECT-OVERVIEW`、错误响应约定 | 路由注册、统一异常处理 |
| `backend/app/config.py`、`database.py` | `PROJECT-ENVIRONMENTS` | 数据路径、CORS、环境变量 |
| `backend/app/models/models.py` | `STATE-ORDER-001`、`DATA-ORDER-001`、术语表 | 18 表、状态字段、索引 |
| `backend/app/schemas/schemas.py` | `API-ORDER-*`、`DATA-ORDER-001` | 请求字段与约束 |
| `backend/app/auth/*` | `PROJECT-ROLES`、`RULE-ORDER-011` | JWT、角色、401/403 |
| `backend/app/seed/seed.py` | `DATA-ORDER-001`、`TEST-DATA` | 种子账号/商品/SKU/券 |
| `backend/app/api/orders.py` | `REQ-ORDER-001`、`FLOW-ORDER-001`、`STATE-ORDER-001`、`RULE-ORDER-001~007`、`RULE-ORDER-011`、`API-ORDER-001~004` | 交易主逻辑 |
| `backend/app/api/payments.py` | `REQ-ORDER-002`、`RULE-ORDER-008`、`RULE-ORDER-009`、`API-ORDER-005`、`STATE-ORDER-001` | 支付与库存扣减 |
| `backend/app/api/admin.py` | `REQ-ORDER-003`、`RULE-ORDER-010`、`RULE-ORDER-011`、`API-ORDER-006`、`STATE-ORDER-001` | 发货、退款审核、Dashboard |
| `backend/app/api/refunds.py` | `STATE-ORDER-001`（退款分支） | 本批不展开退款规则 |
| `backend/app/api/coupons.py` | `RULE-ORDER-004`、`RULE-ORDER-005`、`DATA-ORDER-001` | 领券、券状态 |
| `backend/app/api/cart.py`、`addresses.py` | `RULE-ORDER-002`、`DATA-ORDER-001` 的前置约束 | 下单依赖，只提取最小约束 |
| `frontend/src/App.tsx` | `PROJECT-PLATFORMS`、`AUTO-LOCATOR` | 26 条路由、角色守卫 |
| `frontend/src/pages/product/ProductDetail.tsx` | `FLOW-ORDER-001`、`AUTO-LIMITATIONS`、`CONFLICT-009` | 加购/立即购买行为与缺陷 |
| `frontend/src/pages/cart/Cart.tsx`、`order/OrderConfirm.tsx`、`payment/Payment.tsx` | `FLOW-ORDER-001`、`AUTO-LOCATOR` | 结算与支付路径、sessionStorage |
| `frontend/src/index.css` | `AUTO-LOCATOR` | 业务 CSS 类定位锚点 |
| `Minishop/e2e_test.py` | `AUTO-FRAMEWORK`、`TEST-ENV`、`TEST-SPEC-PROJECT-001` | 48 项行为证据与限制 |
| `Minishop/docker-compose.yml`、`Dockerfile`、`nginx.conf` | `PROJECT-ENVIRONMENTS`、`CONFLICT-005` | 部署形态与构建缺口 |
| `Minishop/data/minishop.db` | `DATA-ORDER-001`、`TEST-DATA` | 当前种子快照 |
| `TestJury_项目知识库数据规范_v1.0.md` | 所有文档的元数据/模板/治理结构 | 外部规范，非项目事实 |

## 3. 规则 → 需求 → 接口 → 流程覆盖矩阵

| 规则 | 需求 | 接口 | 流程/状态 |
|---|---|---|---|
| `RULE-ORDER-001` 金额重算 | `REQ-ORDER-001` | `API-ORDER-001/002` | `FLOW-ORDER-001` |
| `RULE-ORDER-002` 地址归属/快照 | `REQ-ORDER-001` | `API-ORDER-002` | `FLOW-ORDER-001` |
| `RULE-ORDER-003` SKU/库存校验 | `REQ-ORDER-001` | `API-ORDER-001/002` | `FLOW-ORDER-001` |
| `RULE-ORDER-004` 用券资格 | `REQ-ORDER-001` | `API-ORDER-001/002` | `FLOW-ORDER-001` |
| `RULE-ORDER-005` 门槛/应付 | `REQ-ORDER-001` | `API-ORDER-001/002` | `FLOW-ORDER-001` |
| `RULE-ORDER-006` 下单副作用 | `REQ-ORDER-001` | `API-ORDER-002` | `FLOW-ORDER-001`、`STATE-ORDER-001` |
| `RULE-ORDER-007` 取消/券归还 | `REQ-ORDER-004` | `API-ORDER-004` | `STATE-ORDER-001` |
| `RULE-ORDER-008` 支付金额/重复 | `REQ-ORDER-002` | `API-ORDER-005` | `STATE-ORDER-001` |
| `RULE-ORDER-009` 扣库存/销量 | `REQ-ORDER-002` | `API-ORDER-005` | `STATE-ORDER-001` |
| `RULE-ORDER-010` 发货/收货 | `REQ-ORDER-003` | `API-ORDER-004/006` | `STATE-ORDER-001` |
| `RULE-ORDER-011` 越权边界 | `REQ-ORDER-001`、`PROJECT-ROLES` | `API-ORDER-003/004/006` | - |

## 4. 覆盖边界

### 已端到端覆盖

- 下单预览 → 创建 → 支付 → 发货 → 确认收货 → 取消；
- 金额、优惠券、地址、SKU/库存、状态、权限；
- 测试数据准备、环境、接口契约、自动化限制。

### 部分覆盖（只提取下单所需最小约束）

- `auth`：登录与鉴权；
- `catalog`：商品可见性、SKU、价格、库存；
- `cart`：加购与数量校验；
- `address`：地址归属与快照；
- `coupon`：领券与用券资格。

### 未覆盖（登记缺口）

- `after_sales` 退款完整规则；
- `review` 评价；
- `admin` 后台除发货外；
- `messaging`、`favorite`、`inventory`；
- 非功能需求、UI 设计规格、历史缺陷。

## 5. 未提取但可提取的候选

以下内容在代码中存在，但不在本批评审范围，未整理为独立知识：

- `products.py` 的商品/分类后台 CRUD 与 SKU 全量替换；
- `admin.py` 的 Dashboard 统计、用户启停、库存调整、评价删除；
- `refunds.py` 的退款申请/查询；
- `reviews.py` 的评价创建/列表；
- `messages.py`、`favorites.py`；
- `seed.py` 的图片生成逻辑（已知格式缺陷）。

这些在 `knowledge_gaps.yaml#GAP-011` 中登记，不得从本批文档推断。
