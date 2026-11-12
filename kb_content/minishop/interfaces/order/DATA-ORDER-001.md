---
id: DATA-ORDER-001
title: 订单与支付相关数据结构及测试数据准备
knowledge_type: INTERFACE
project_id: minishop
module_id: order
source_type: DATABASE_SCHEMA
source_ref: Minishop/backend/app/models/models.py#L171-L243; Minishop/backend/app/models/models.py#L140-L165; Minishop/backend/app/seed/seed.py#L38-L151; Minishop/data/minishop.db
source_version: snapshot-2026-11-11
product_version:
  - "1.0.0"
platforms:
  - all
evidence_level: E2
status: approved
owner: minishop_project_team
reviewer: "平台设计者（技术负责人）"
created_at: 2026-11-11
updated_at: 2026-11-12
effective_from: null
effective_until: null
reviewed_at: 2026-11-11
review_cycle_days: 90
change_reason: "2026-11-12：澄清 user_coupons.EXPIRED 为读取时计算值、优惠券可用列标注快照日期并要求动态判断；保留人工复核通过记录；本轮仅合并重复变更字段"
tags:
  - order
  - data
  - schema
  - seed
  - test_data
related_ids:
  - API-ORDER-001
  - API-ORDER-002
  - API-ORDER-005
  - RULE-ORDER-006
  - TEST-DATA
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
---

# 1. 数据对象与表

| 对象 | 表 | 作用 |
|---|---|---|
| 订单 | `orders` | 订单主表、金额、状态、地址快照 |
| 订单明细 | `order_items` | 商品/SKU 快照、成交价、数量 |
| 支付 | `payments` | 支付单、金额、状态 |
| 物流 | `shipments` | 物流公司、运单号、物流状态 |
| 售后 | `refunds` | 退款申请与审核（跨模块） |
| 用户券 | `user_coupons` | 券的领取与使用状态 |
| 券模板 | `coupons` | 门槛、面额、有效期、发放量 |
| 商品/SKU | `products`、`product_skus` | 价格、库存、销量、上下架 |
| 库存日志 | `inventory_logs` | 支付扣减、退款恢复、人工调整 |
| 消息 | `messages` | 支付成功、发货、退款结果通知 |

当前库共 18 张表；与交易域直接相关的为上述 11 张（`products` 与 `product_skus` 分开计）。

# 2. 订单表 `orders`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | int | PK，自增 | 订单 ID |
| `order_no` | string(64) | 唯一、非空、索引 | 14 位时间戳 + 6 位随机数 |
| `user_id` | int | FK users，索引 | 订单所有者 |
| `status` | string(32) | 默认 `PENDING_PAYMENT` | 见状态枚举 |
| `total_amount` | float | 默认 0 | 商品总金额 |
| `discount_amount` | float | 默认 0 | 优惠金额 |
| `pay_amount` | float | 默认 0 | 应付金额 |
| `receiver_name` | string(64) | 默认空 | 收货人快照 |
| `phone` | string(32) | 默认空 | 电话快照 |
| `address_snapshot` | text | 默认 `{}` | 地址 JSON 快照 |
| `user_coupon_id` | int | 默认 0 | 用户券 ID，0 表示未用券 |
| `created_at` | datetime | 默认当前时间 | 创建时间 |
| `paid_at` | datetime | 可空 | 支付时间 |
| `shipped_at` | datetime | 可空 | 发货时间 |
| `completed_at` | datetime | 可空 | 完成时间 |
| `cancelled_at` | datetime | 可空 | 取消时间 |

# 3. 订单明细 `order_items`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | int | PK | 明细 ID |
| `order_id` | int | FK orders，索引 | 所属订单 |
| `product_id` | int | 无 FK | 商品 ID |
| `sku_id` | int | 无 FK | SKU ID |
| `product_name_snapshot` | string(128) | 默认空 | 商品名快照 |
| `spec_snapshot` | text | 默认 `{}` | 规格 JSON 快照 |
| `price` | float | 默认 0 | 成交单价（SKU 价） |
| `quantity` | int | 默认 1 | 数量 |
| `subtotal` | float | 默认 0 | 小计 |

`product_id`、`sku_id` **没有数据库外键**，商品删除后明细仍保留快照值。

# 4. 支付与物流

## `payments`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | int | PK | 支付记录 ID |
| `order_id` | int | FK orders，索引，**非唯一** | 同一订单可多条 |
| `payment_no` | string(64) | 唯一、索引 | 支付单号 |
| `method` | string(32) | 默认 `WECHAT` | 无枚举约束 |
| `amount` | float | 默认 0 | 支付金额 |
| `status` | string(16) | 默认 `PENDING` | `PENDING/SUCCESS/FAILED` |
| `paid_at` | datetime | 可空 | 支付时间 |
| `created_at` | datetime | 默认当前时间 | 创建时间 |

## `shipments`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | int | PK | 物流单 ID |
| `order_id` | int | FK orders，索引 | 所属订单 |
| `company` | string(64) | 默认空 | 物流公司 |
| `tracking_number` | string(64) | 默认空 | 运单号 |
| `status` | string(16) | 默认 `SHIPPED` | `SHIPPED/DELIVERED` |
| `shipped_at` | datetime | 默认当前时间 | 发货时间 |

# 5. 关联数据

## `user_coupons`

`id`、`user_id`、`coupon_id`、`status`、`used_order_id`、`received_at`、`used_at`。

- 数据库实际只会写入 `UNUSED` / `USED`；`EXPIRED` **不是存储值**，而是读取时由 `coupons.end_time` 动态计算（`coupons.py#L19-L22`），模型注释中的 `EXPIRED` 仅表示展示态；
- 下单时置 `USED` 并写 `used_order_id`；
- 取消订单时恢复 `UNUSED`、`used_order_id=0`、`used_at=NULL`；
- 退款不恢复券（当前实现）。

## `coupons`

`id`、`name`、`type`（默认 `FULL_REDUCTION`）、`threshold`、`discount_amount`、`start_time`、`end_time`、`total_quantity`、`used_quantity`、`status`（`ACTIVE/DISABLED`）。

- `used_quantity` 在**下单用券**时 +1，取消时 -1；领券时不增加；
- `start_time` 在领券和用券时都**没有校验**；
- `end_time` 在领券和用券时校验；
- 已确认（Q-06）：`total_quantity` 语义为**发放总量**；当前领券按 `used_quantity` 判断、领券不计数，属已确认待修复不一致（CONFLICT-006）。

## `products` / `product_skus`

- 下单校验 `product_skus.stock`，不校验 `products.stock`；
- 支付成功同时扣减两者并增加 `products.sales`；
- 多规格商品的 `products.stock` 是聚合值，可能与 SKU 之和漂移。

## `inventory_logs`

`product_id`、`sku_id`、`change_quantity`、`before_quantity`、`after_quantity`、`reason`、`operator_id`、`created_at`。

## `messages`

`user_id`、`title`、`content`、`type`、`is_read`、`created_at`。支付成功、发货、退款审核会产生消息。

# 6. 状态枚举

| 枚举 | 允许值 |
|---|---|
| 订单状态 | `PENDING_PAYMENT`、`PAID`、`PENDING_SHIPMENT`、`SHIPPED`、`COMPLETED`、`CANCELLED`、`REFUNDING`、`REFUNDED` |
| 支付状态 | `PENDING`、`SUCCESS`、`FAILED` |
| 物流状态 | `SHIPPED`、`DELIVERED` |
| 用户券状态 | `UNUSED`、`USED`、`EXPIRED` |
| 退款状态 | `PENDING`、`APPROVED`、`REJECTED`、`REFUNDED` |

数据库层**没有** CHECK 约束，枚举靠代码维护。

# 7. 种子数据基线

## 7.1 账号

| 用户名 | 密码 | 角色 |
|---|---|---|
| `admin` | `admin123` | `ADMIN` |
| `user` | `123456` | `USER` |

## 7.2 商品与 SKU（当前库）

| 商品 ID | 名称 | 单价 | 库存 | 销量 | SKU |
|---:|---|---:|---:|---:|---|
| 1 | iPhone 17 | 5999 | 20 | 120 | 1 个默认 SKU |
| 2 | 小米手机 | 2999 | 10 | 300 | 1 个 |
| 3 | 华为平板 | 3999 | 5 | 80 | 1 个 |
| 4 | MacBook | 8999 | 8 | 45 | 1 个 |
| 5 | 机械键盘 | 399 | 50 | 560 | 1 个 |
| 6 | 无线鼠标 | 199 | 0 | 900 | 1 个（售罄） |
| 7 | 蓝牙耳机 | 599 | 1 | 430 | 1 个（库存边界） |
| 8 | 运动鞋 | 499 | 14 | 760 | 8 个（黑/白 × 39–42） |
| 9 | 咖啡 | 59 | 100 | 1200 | 1 个 |

运动鞋 8 个 SKU 的库存：黑 39/40/41/42 = 2/2/2/2；白 39/40/41/42 = 1/1/2/2，合计 14。

## 7.3 优惠券（当前库，播种于 2026-09-21）

| ID | 名称 | 门槛 | 优惠 | 结束时间 | 状态 | 快照日 2026-11-11 可用 |
|---:|---|---:|---:|---|---|:---:|
| 1 | 新人满100减10 | 100 | 10 | 2026-10-21 | ACTIVE | ❌ 已过期 |
| 2 | 满1000减100 | 1000 | 100 | 2026-11-20 | ACTIVE | ✅ |
| 3 | 满5000减500 | 5000 | 500 | 2026-12-20 | ACTIVE | ✅ |
| 4 | 满50减5(已过期) | 50 | 5 | 2026-09-20 | DISABLED | ❌ |

> “可用”列只对快照日 2026-11-11 成立（券 2 于 2026-11-20 到期）。判断当前可用性必须用 `end_time` 与执行日期比较，或调用 `GET /api/coupons/available`，不得直接引用本列。
> 重新播种会按“播种时间 + 相对天数”生成有效期，券的可用状态可能不同。测试不得假设券 ID 或可用性固定。

# 8. 测试数据准备

## 8.1 隔离数据库（推荐）

```powershell
cd Minishop\backend
$env:DATABASE_URL='sqlite:///./verify.db'
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- `verify.db` 会在 `backend/` 下创建，启动时自动建表 + 播种。
- 验证结束后停止服务并删除 `verify.db`。
- 不要直接在共享的 `data/minishop.db` 上跑会写数据的自动化。

## 8.2 步骤

### 步骤 1：登录

```http
POST /api/auth/login
{"username": "user", "password": "123456"}
```

取 `data.token` 作为后续 `Authorization: Bearer <token>`。

### 步骤 2：创建地址

```http
POST /api/addresses
{"receiver_name":"张三","phone":"13800138000","province":"广东省","city":"深圳市","district":"南山区","detail_address":"科技园路1号","is_default":true}
```

取 `data.id` 作为 `address_id`。

### 步骤 3：解析商品与 SKU

```http
GET /api/products?keyword=机械键盘
```

取 `data.items[0].skus[0].id` 作为 `sku_id`，并记录 `price` 与 `stock`。

> 不要硬编码 SKU ID。当前种子库中机械键盘 SKU 为 5，但重建数据库后会变化。

### 步骤 4（可选）：加购

```http
POST /api/cart/items
{"sku_id": <sku_id>, "quantity": 3}
```

订单接口不要求先加购；加购只用于验证购物车与下单的衔接。

### 步骤 5：领券并获取用户券 ID

```http
GET /api/coupons/available
POST /api/coupons/{coupon_id}/claim
GET /api/coupons/my
```

取 `data[].id` 作为 `user_coupon_id`（注意是用户券 ID，不是券模板 ID）。
当前库中券 1 已过期，优先使用券 2（满1000减100）或券 3（满5000减500）。

### 步骤 6：预览与创建

```http
POST /api/orders/preview
{"items":[{"sku_id": <sku_id>, "quantity": 3}], "address_id": <address_id>, "user_coupon_id": <user_coupon_id>}

POST /api/orders
{"items":[{"sku_id": <sku_id>, "quantity": 3}], "address_id": <address_id>, "user_coupon_id": <user_coupon_id>}
```

### 步骤 7：支付、发货、确认

```http
POST /api/payments                     {"order_id": <order_id>, "method": "WECHAT"}
POST /api/payments/{payment_id}/success
POST /api/admin/orders/{order_id}/ship {"company":"顺丰","tracking_number":"SF123456789"}   # 需 admin token
POST /api/orders/{order_id}/confirm
```

# 9. 重置与隔离

| 方式 | 操作 | 影响 |
|---|---|---|
| 重置共享库 | 停止后端，删除 `data/minishop.db`，重启 | 清空全部运行数据，重新播种 |
| 独立库 | `DATABASE_URL=sqlite:///./verify.db` | 与共享库隔离，推荐自动化使用 |
| 独立用户 | 每次 `POST /api/auth/register` 唯一用户名 | 避免订单/券数据互相污染 |
| 独立 SKU | 选择不同商品/SKU | 避免库存被其他用例消耗 |

注意事项：

- `e2e_test.py` 会创建用户、订单、退款、评价，必须使用独立库。
- 券有效期依赖播种时间，跨日期执行可能失败。
- 订单、支付、退款 ID 自增，不能跨环境硬编码。

# 10. 查询验证与缺口

## 10.1 验证 SQL

```sql
SELECT id, order_no, status, total_amount, discount_amount, pay_amount FROM orders WHERE id = ?;
SELECT * FROM order_items WHERE order_id = ?;
SELECT id, payment_no, amount, status, paid_at FROM payments WHERE order_id = ?;
SELECT company, tracking_number, status FROM shipments WHERE order_id = ?;
SELECT status, used_order_id, used_at FROM user_coupons WHERE id = ?;
SELECT stock FROM product_skus WHERE id = ?;
SELECT stock, sales FROM products WHERE id = ?;
SELECT change_quantity, before_quantity, after_quantity, reason FROM inventory_logs WHERE sku_id = ? ORDER BY id DESC LIMIT 5;
```

## 10.2 已知数据约束缺口

- `order_items.product_id/sku_id` 无外键，商品删除后无法从明细反查商品；
- `payments.order_id` 非唯一，同一订单可多条支付记录；
- 订单/支付/退款状态无数据库 CHECK 约束；
- 金额使用 float；
- 无数据库迁移脚本，表结构变更无法追溯；
- 无测试数据重置 API，只能删库或换库。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：表结构/枚举/无 CHECK 约束/order_items 的 product_id 与 sku_id 无外键（models.py:201-202）一致；种子基线经只读实测全部吻合（18 表、2 账号、9 商品、运动鞋总库存 14 与 8 SKU 分布、4 券）；领券/用券只校验 end_time、used_quantity 增减路径、无 alembic 迁移均属实。
- **复核备注**：微调：§1"与交易域直接相关的为上述 10 张"实为 11 张（products 与 product_skus 合写一行）；补记 Q-06 已知缺口（领券额度按 used_quantity 判断与发放总量语义不一致）。设计者复核另发现券#1 已自然过期，详见 PROJECT-VERSIONS 备注。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
