---
id: AUTO-LOCATOR
title: 自动化定位与断言约定
knowledge_type: AUTOMATION
project_id: minishop
module_id: null
source_type: AUTOMATION_DOC
source_ref: Minishop/frontend/src/index.css#L14-L90; Minishop/frontend/src/pages/login/Login.tsx#L33-L68; Minishop/frontend/src/pages/product/ProductDetail.tsx#L121-L155; Minishop/e2e_test.py#L11-L180
source_version: snapshot-2026-11-11
product_version:
  - "1.0.0"
platforms:
  - all
evidence_level: E3
status: approved
owner: minishop_project_team
reviewer: "平台设计者（技术负责人）"
created_at: 2026-11-11
updated_at: 2026-11-12
effective_from: null
effective_until: null
reviewed_at: 2026-11-11
review_cycle_days: 90
tags:
  - automation
  - locator
  - assertion
  - api
  - ui
related_ids:
  - AUTO-FRAMEWORK
  - AUTO-LIMITATIONS
  - TEST-SPEC-PROJECT-001
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 定位原则

1. **优先接口，其次 UI**：交易域的状态、金额、库存、权限都能通过 API + DB 稳定断言。
2. **优先语义定位**：角色、文本、占位符、业务 CSS 类；避免 AntD 生成的哈希类名。
3. **避免位置定位**：不要依赖 `div:nth-child(3)`。
4. **等待可观察信号**：等待接口响应或元素可见，不用固定 `sleep`。
5. **断言可区分层次**：HTTP 层、业务码层、数据层、副作用层分开断言。

# 2. API 定位与断言

## 2.1 请求构造

- Base URL：`http://127.0.0.1:8000/api`（本地）或同源 `/api`（前端代理）；
- 认证：`Authorization: Bearer <token>`；
- JSON：`Content-Type: application/json`；
- 业务 ID 通过查询接口获得，不硬编码。

```python
import requests

BASE = "http://127.0.0.1:8000/api"

def login(username, password):
    r = requests.post(f"{BASE}/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["data"]["token"]
```

## 2.2 断言层次

| 层次 | 断言内容 | 示例 |
|---|---|---|
| HTTP | 状态码 | `r.status_code == 409` |
| 业务码 | `code` | `r.json()["code"] == "OK"` |
| 消息 | `message` | `"库存不足" in r.json()["message"]` |
| 数据 | 字段值 | `data["status"] == "PENDING_PAYMENT"` |
| 金额 | 容差比较 | `abs(pay - 1187.0) < 0.01` |
| 副作用 | 数据库/再次查询 | SKU 库存减少 3、券变 `USED` |
| 状态机 | 合法/非法转换 | 重复支付返回 409 |

## 2.3 推荐的断言工具

```python
def assert_amount(actual, expected, tol=0.01):
    assert abs(float(actual) - float(expected)) <= tol, (actual, expected)
```

- 金额不要用字符串相等；
- 时间不要断言具体值，断言非空/顺序；
- 订单号/支付单号不要断言固定值，断言格式/唯一性；
- 错误消息断言关键片段，避免全量文案耦合。

## 2.4 数据库断言

```python
import sqlite3

db = sqlite3.connect(r"Minishop\data\minishop.db")
row = db.execute("SELECT status, pay_amount FROM orders WHERE id=?", (order_id,)).fetchone()
assert row[0] == "PENDING_PAYMENT"
```

- 自动化使用独立库（`DATABASE_URL=sqlite:///./verify.db`）；
- 查询前确保后端已提交事务；
- 不要长时间持有连接，SQLite 写锁会影响后端。

# 3. UI 定位

## 3.1 可用定位锚点

### 登录页

| 目标 | 定位建议 |
|---|---|
| 用户名输入 | `get_by_placeholder("用户名")` |
| 密码输入 | `get_by_placeholder("密码")` |
| 登录按钮 | `get_by_role("button", name="登 录")` |
| 注册标签 | `get_by_role("tab", name="注册")` |
| 注册用户名 | `get_by_placeholder("用户名（≥3位）")` |
| 注册密码 | `get_by_placeholder("密码（≥6位）")` |
| 注册按钮 | `get_by_role("button", name="注 册")` |

### 商品详情

| 目标 | 定位建议 |
|---|---|
| 规格标签 | `.spec-tag`（选中 `.spec-tag.selected`，禁用 `.spec-tag.disabled`） |
| 数量输入 | `.ant-input-number input` |
| 加购按钮 | `get_by_role("button", name="加入购物车")` |
| 立即购买 | `get_by_role("button", name="立即购买")` |
| 收藏 | `get_by_role("button", name=re.compile("收藏|已收藏"))` |
| 商品图 | `img.product-card-image` / 详情页 `img`（当前图损坏，勿断言渲染） |

### 购物车

| 目标 | 定位建议 |
|---|---|
| 表格 | `.ant-table` |
| 行 | `.ant-table-tbody tr` |
| 数量输入 | 行内 `.ant-input-number input` |
| 删除按钮 | 行内 `.ant-btn-dangerous` + 确认气泡 `.ant-popconfirm` |
| 去结算 | `get_by_role("button", name="去结算")` |
| 勾选 | `.ant-checkbox-input` |

### 结算/支付/订单

| 目标 | 定位建议 |
|---|---|
| 地址单选 | `.ant-radio-group .ant-radio-wrapper` |
| 优惠券单选 | 同上，按文本“满X减Y” |
| 提交订单 | `get_by_role("button", name="提交订单")` |
| 模拟支付成功 | `get_by_role("button", name=re.compile("模拟支付成功"))` |
| 模拟支付失败 | `get_by_role("button", name=re.compile("模拟支付失败"))` |
| 订单状态标签 | `.ant-tag`（文本“待支付/已支付/已发货/已完成/已取消/退款中/已退款”） |
| 确认收货 | `get_by_role("button", name="确认收货")` |
| 取消订单 | `get_by_role("button", name="取消订单")` |

### 管理后台

| 目标 | 定位建议 |
|---|---|
| 侧边菜单 | `.ant-menu-item` 按文本 |
| 订单表格 | `.ant-table` |
| 发货按钮 | 行内 `get_by_role("button", name=re.compile("发货"))` |
| 物流弹窗 | `.ant-modal`，输入 `company` / `tracking_number` 对应表单项 |

## 3.2 不应使用的定位

- `div:nth-child(n)`、绝对 XPath；
- AntD 哈希类名（如 `css-1x2y3z`）；
- 依赖商品图 `src`（当前 SVG 非法）；
- 依赖具体订单号文本（动态生成）；
- 依赖 Toast 文案全文（易变）。

# 4. 等待策略

| 场景 | 建议 |
|---|---|
| 登录跳转 | 等待 URL 变化或用户菜单出现 |
| 商品列表加载 | 等待 `.ant-card` 数量 > 0 |
| 提交订单 | 等待响应 `POST /api/orders` 201 或跳转 `/payment/` |
| 支付成功 | 等待订单详情状态标签变化或 URL 跳转 |
| 表格刷新 | 等待行文本变化，不用固定 sleep |
| AntD 弹窗 | 等待 `.ant-modal` 可见，操作后等待关闭 |

# 5. UI 断言

- 元素可见/不可见；
- 文本包含；
- 按钮 `disabled` 状态；
- 表格行数与关键列文本；
- URL 路径；
- localStorage 登录态（`minishop_token`、`minishop_user`）；
- 不把“图片加载成功”作为断言（当前图片格式非法）。

# 6. 推荐的用例-知识映射

| 用例主题 | 知识 ID |
|---|---|
| 金额计算 | `RULE-ORDER-001`、`RULE-ORDER-005` |
| 库存边界 | `RULE-ORDER-003`、`RULE-ORDER-009` |
| 优惠券 | `RULE-ORDER-004`、`RULE-ORDER-005` |
| 取消 | `RULE-ORDER-007` |
| 支付 | `RULE-ORDER-008`、`RULE-ORDER-009` |
| 发货/收货 | `RULE-ORDER-010` |
| 越权 | `RULE-ORDER-011` |
| 状态流转 | `STATE-ORDER-001` |

# 7. 备注

- 以上 UI 定位基于当前源码与 CSS，仓库**没有** `data-testid`，文本/类名变更会导致定位失效；
- Playwright/Cypress 未安装，示例为建议写法，未在本项目验证；
- 自动化前请先阅读 `AUTO-LIMITATIONS`，确认当前不可自动化的场景。

> 复核补充：金额样例 `abs(pay-1187.0)<0.01` 依赖已过期新人券；重建种子库后成立，否则用券#2 → 1097.0。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：全部定位锚点均有源码出处：Login.tsx:36-74、ProductDetail.tsx:129-154 与 index.css:69-87（.spec-tag/selected/disabled）、Cart.tsx:83-111、Payment.tsx:53-56、OrderConfirm.tsx:80-138、AdminOrders.tsx:105-110、auth.tsx:45-46（minishop_token/minishop_user）。
- **复核备注**：:75 的金额断言范式 abs(pay-1187.0)<0.01 依赖已过期的新人券，须加注"重建种子库后成立；否则机械键盘×3 用券#2 → 1097.0"。另需注明无 data-testid，定位依赖中文文案与 class，文案变更即失效。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
