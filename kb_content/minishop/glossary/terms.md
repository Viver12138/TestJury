---
id: GLOSSARY-001
title: MiniShop 业务术语表
knowledge_type: GLOSSARY
project_id: minishop
module_id: null
source_type: OTHER
source_ref: Minishop/README.md#L46-L107; Minishop/backend/app/models/models.py#L20-L326; Minishop/frontend/src/pages/product/ProductDetail.tsx
source_version: snapshot-2026-11-11
product_version:
  - "1.0.0"
platforms:
  - all
evidence_level: E2
status: approved
owner: minishop_project_team
reviewer: "平台设计者（产品负责人）"
created_at: 2026-11-11
updated_at: 2026-11-12
effective_from: null
effective_until: null
reviewed_at: 2026-11-11
review_cycle_days: 90
tags:
  - glossary
  - terms
  - domain
related_ids:
  - PROJECT-OVERVIEW
  - DATA-ORDER-001
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 术语表

| 术语 | 定义 | 相关字段/接口 | 备注 |
|---|---|---|---|
| SUT | 被测系统（System Under Test） | - | 本项目整体作为被测对象 |
| 商品 | 可售卖条目，包含名称、描述、主价格、主图、上下架状态、销量 | `products` | 一个商品可有多个 SKU |
| SKU | 最小库存/价格单位，对应具体规格组合 | `product_skus` | 单规格商品也有 1 个默认 SKU，`spec_values={}` |
| 规格 | SKU 的属性键值，如 `{"颜色":"黑色","尺码":"39"}` | `product_skus.spec_values` | JSON 字符串存储 |
| 库存 | SKU 可售数量；商品上另有聚合库存 | `product_skus.stock`、`products.stock` | 下单只校验 SKU 库存 |
| 销量 | 商品累计销售数量 | `products.sales` | 支付成功 +quantity，退款成功 -quantity |
| 上架/下架 | 商品是否可被前台查询和购买 | `products.status`：`ON_SALE`/`OFF_SALE` | 下架商品详情返回 404 |
| 购物车 | 用户待购买 SKU 的集合 | `carts` | 同 SKU 合并；下单不清空 |
| 地址 | 用户收货信息 | `addresses` | 每用户最多一个默认地址（应用层保证） |
| 默认地址 | 用户标记为首选的地址 | `addresses.is_default` | 下单不强制使用默认地址 |
| 优惠券模板 | 平台发放的券定义 | `coupons` | 含门槛、面额、有效期、发放量 |
| 用户券 | 用户领取到的券实例 | `user_coupons` | 下单时使用其 `id` |
| 门槛 | 使用券所需的最低商品总金额 | `coupons.threshold` | 按优惠前金额比较 |
| 满减 | 达到门槛后减固定金额 | `coupons.discount_amount` | 当前只支持这一种类型 |
| 领券 | 用户把券模板领取为自己的用户券 | `POST /api/coupons/{id}/claim` | 同一用户同一模板只能领一次 |
| 用券 | 下单时把用户券置为已使用 | `POST /api/orders` | 取消订单会归还 |
| 优惠金额 | 本单因用券减免的金额 | `orders.discount_amount` | 等于券面额 |
| 商品总金额 | 各明细 `sku.price × quantity` 之和 | `orders.total_amount` | 服务端计算 |
| 应付金额 | 商品总金额减优惠金额，最低 0 | `orders.pay_amount` | 支付金额来源 |
| 订单 | 一次交易的凭据，含金额、状态、地址/商品快照 | `orders` | 状态见下 |
| 订单号 | 订单业务编号 | `orders.order_no` | 14 位时间戳 + 6 位随机数 |
| 订单明细 | 订单中的商品行 | `order_items` | 保存商品名/规格/价格快照 |
| 快照 | 下单时固化的地址或商品信息 | `address_snapshot`、`order_items.*_snapshot` | 后续源数据变化不影响订单 |
| 支付单 | 一次模拟支付记录 | `payments` | 同一订单可有多条（失败重试） |
| 模拟支付 | 不接真实渠道，手动标记成功/失败 | `/api/payments/*` | 仅用于演示与测试 |
| 支付成功 | 支付单置 `SUCCESS`，订单置 `PAID` | `POST /api/payments/{id}/success` | 触发库存扣减 |
| 支付失败 | 支付单置 `FAILED`，订单仍待支付 | `POST /api/payments/{id}/fail` | 可重新支付 |
| 重复支付 | 对已支付订单再次支付 | - | 返回 409，不重复扣库存 |
| 发货 | 管理员录入物流信息，订单置 `SHIPPED` | `POST /api/admin/orders/{id}/ship` | 仅管理员 |
| 物流单 | 订单对应的物流公司与运单号 | `shipments` | 确认收货后置 `DELIVERED` |
| 运单号 | 物流公司提供的包裹编号 | `shipments.tracking_number` | 无格式校验 |
| 确认收货 | 用户确认收到货，订单置 `COMPLETED` | `POST /api/orders/{id}/confirm` | 仅已发货订单 |
| 取消订单 | 待支付订单置 `CANCELLED` | `POST /api/orders/{id}/cancel` | 归还优惠券 |
| 退款/售后 | 支付后申请退回款项 | `refunds` | 本批未完整覆盖 |
| 退款中 | 退款申请待审核 | `orders.status=REFUNDING` | 不可发货/确认 |
| 已退款 | 退款审核通过 | `orders.status=REFUNDED` | 库存恢复（跨模块） |
| 评价 | 已完成订单的商品评分与内容 | `reviews` | 每个订单明细只能评价一次 |
| 站内消息 | 支付、发货、退款等业务通知 | `messages` | 只读/标记已读 |
| 库存日志 | 库存变化的审计记录 | `inventory_logs` | 支付扣减、退款恢复、人工调整 |
| 管理员 | 可访问 `/api/admin/**` 的角色 | `users.role=ADMIN` | 不能禁用管理员账号 |
| 普通用户 | 只能操作自己数据的角色 | `users.role=USER` | 种子账号 `user` |
| JWT | 登录后签发的访问令牌 | `Authorization: Bearer` | HS256，24 小时 |
| 种子数据 | 首次启动自动写入的演示数据 | `seed.py` | 幂等 |
| 幂等 | 同一操作重复执行不产生额外副作用 | - | 本项目多数写接口**不幂等** |
| 超卖 | 卖出数量超过实际库存 | - | 当前架构存在该风险，见 `EXP-ORDER-001` |
| 状态机 | 订单状态与合法转换的集合 | `STATE-ORDER-001` | 含不可达状态 `PENDING_SHIPMENT` |
| 数据库迁移 | 表结构版本化变更脚本 | - | 本项目没有 |
| 测试用例 | 待评审的测试设计对象 | - | 不属于知识库事实源 |
| 知识缺口 | 缺少某类可追溯资料 | - | 见 `_governance/knowledge_gaps.yaml` |

# 2. 易混淆术语

| 容易混淆 | 区分 |
|---|---|
| 商品价格 vs SKU 价格 | 下单按 SKU 价格；商品主价格只用于展示/兜底 |
| 商品库存 vs SKU 库存 | 下单校验 SKU 库存；聚合库存不是强一致 |
| 优惠券模板 ID vs 用户券 ID | 下单接口的 `user_coupon_id` 必须是用户券 ID |
| 待发货 `PENDING_SHIPMENT` vs 已支付 `PAID` | 前者代码从未赋值，实际不可达 |
| 支付失败 vs 订单失败 | 支付失败后订单仍待支付，可重试 |
| 取消 vs 退款 | 取消只针对待支付；退款针对支付后 |
| 退款中 vs 已退款 | 前者待审核，后者终态且恢复库存 |

# 3. 来源与未决问题

- 术语定义来自 README 功能说明、代码字段与接口行为；
- 没有项目官方术语表，本表为整理稿，需业务负责人确认；
- “超卖”“幂等”等为测试/架构术语，不是项目业务文案。

> 复核补充：`total_quantity` 语义应为发放总量；当前 `coupons.py#L83` 按 `used_quantity` 判“已领完”，属已确认待修复不一致（Q-06）。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：术语与字段/接口逐条对应（models.py、common.py:20 订单号 14+6、orders.py、payments.py、admin.py、coupons.py、seed.py）；PENDING_SHIPMENT 从未赋值、超卖与 max 截断扣减描述一致。
- **复核备注**：非阻塞建议：在"优惠券模板/发放量"条目补现状备注——total_quantity 语义应为发放总量，当前 coupons.py:83 按 used_quantity 判"已领完"，属已确认待修复不一致（Q-06）。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
