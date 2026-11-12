---
id: EXP-ORDER-001
title: 交易域代码走查风险线索
knowledge_type: EXPERT_KNOWLEDGE
project_id: minishop
module_id: order
source_type: EXPERT_REVIEW
source_ref: Minishop/backend/app/api/orders.py; Minishop/backend/app/api/payments.py;
  Minishop/backend/app/api/admin.py; Minishop/backend/app/api/refunds.py; Minishop/frontend/src/pages/product/ProductDetail.tsx
source_version: snapshot-2026-11-11
product_version:
- 1.0.0
platforms:
- all
evidence_level: E4
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
- order
- risk
- expert
- code_review
related_ids:
- RULE-ORDER-003
- RULE-ORDER-008
- RULE-ORDER-009
- CONFLICT-002
- CONFLICT-010
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: delegated_review_completed
change_reason: 2026-11-12 用户授权技术复核；具体依据见 evidence/M2/delegated_content_review.json
---

# 1. 性质声明

本文是**代码走查得到的风险线索**，证据等级 `E4`：

- 不是业务规则；
- 不能单独作为业务 blocker 的依据；
- 需要业务/测试负责人确认后，才能转化为正式规则或缺陷记录；
- 每条风险都给出了代码位置，便于复核。

# 2. 风险清单

## R-01 超卖风险

**观察**：下单只校验 SKU 库存，不扣减/不锁定；支付成功才扣库存，且使用 `max(stock - quantity, 0)`，库存不足不报错。

**证据**：`orders.py#L45-L59`、`payments.py#L15-L36`、`payments.py#L92-L102`。

**影响**：两个待支付订单可以同时买走最后 1 件；第二笔支付成功但库存为 0，销量仍增加。

**建议用例**：库存 1 的蓝牙耳机，两个用户各建一笔订单，依次支付，断言第二笔是否应失败、库存/销量/日志是否符合预期。

**关联**：`RULE-ORDER-003`、`RULE-ORDER-009`、`CONFLICT-002`。

## R-02 重复下单

**观察**：创建订单无幂等键、无防重复提交；相同请求会生成多张订单。

**证据**：`orders.py#L116-L170`。

**影响**：用户双击/网络重试会产生重复订单；测试不能假设“只创建一张”。

**建议用例**：同一请求连续提交两次（不使用券），断言订单数量与订单号不同。

**关联**：`RULE-ORDER-006`。

## R-03 下单不清空购物车

**观察**：创建订单只写订单与明细，不删除购物车项。

**证据**：`orders.py#L116-L170`；前端 `OrderConfirm.tsx#L47-L62`。

**影响**：用户下单后购物车仍有商品，可能重复下单；测试需明确这是当前行为还是缺陷。

**建议用例**：加购 → 下单 → 查询购物车，断言商品仍在（当前行为）。

**关联**：`REQ-ORDER-001`、`RULE-ORDER-006`。

## R-04 优惠券发放量语义不一致

**观察**：`total_quantity` 与“优惠券已领完”提示暗示发放上限，但领券不增加 `used_quantity`，只有下单用券才增加；可用券查询又按“已用 + 当前用户已领”判断。

**证据**：`coupons.py#L40-L88`、`orders.py#L161-L166`。

**影响**：可无限领取，直到用券次数达到上限；“领完”场景难以构造。

**建议用例**：构造 `total_quantity=1` 的券，两个用户领取，观察是否都能领；再分别使用，观察第二次是否失败。

**关联**：`RULE-ORDER-004`、`RULE-ORDER-005`、`CONFLICT-006`。

## R-05 退款拒绝后订单状态回退

**观察**：退款申请允许 `PAID/SHIPPED/COMPLETED`；拒绝时统一把订单改回 `PAID`。

**证据**：`refunds.py#L14-L41`、`admin.py#L226-L245`。

**影响**：已发货/已完成订单退款被拒后丢失 `SHIPPED`/`COMPLETED` 事实，物流单仍存在但订单显示已支付，状态机不自洽。

**建议用例**：已发货订单申请退款 → 管理员拒绝 → 断言订单状态与物流状态。

**关联**：`STATE-ORDER-001`、`CONFLICT-010`。

## R-06 多支付记录与单对象关系

**观察**：同一订单可有多条 `payments`（失败重试），但 `Order.payment` 是 `uselist=False`。历史复核观察到 FAILED+SUCCESS 场景返回 FAILED 并抛 SAWarning；无排序关系不保证固定选取哪一条，当前实现不满足成功/最新支付的目标。

**证据**：`models.py#L192`、`payments.py#L50-L74`、`backend/app/api/common.py#L164-L174`。

**影响**：支付失败后再成功，订单详情可能显示 `FAILED`；自动化断言可能不稳定。

**建议用例**：支付失败 → 再创建支付并成功 → 查询订单详情，断言 `payment.status` 的期望值（当前需确认）。

**关联**：`RULE-ORDER-008`、`CONFLICT-007`。

## R-07 前端主流程缺陷

**观察**：

1. 单规格商品 `spec_values={}`，`selected` 永远为空，`currentSku` 为 `undefined`，详情页无法加购；
2. 种子商品图 SVG 的 `font-family` 引号嵌套导致 XML 非法，且 data URL 未编码；
3. 结算页商品来自 sessionStorage；同一标签页普通刷新会保留。新会话、清空存储或没有 checkout_items 时直达无法恢复商品。

**证据**：`ProductDetail.tsx#L45-L77`、`seed.py#L12-L25`、`OrderConfirm.tsx#L21-L24`。

**影响**：UI 自动化无法购买 8/9 个商品；图片断言必然失败；结算页不可直达。

**建议用例**：UI 主流程使用运动鞋（多规格）；API 用例不受影响。

**关联**：`CONFLICT-001`、`CONFLICT-009`、`AUTO-LIMITATIONS`。

## R-08 Dashboard 销售额口径

**观察**：`sales_amount` 统计 `PAID/PENDING_SHIPMENT/SHIPPED/COMPLETED/REFUNDING/REFUNDED` 订单的 `pay_amount`，同时 `refund_amount` 单独统计已退款。

**证据**：`admin.py#L28-L33`。

**影响**：已退款订单同时计入销售额和退款额，销售额未扣减；统计类断言需确认口径。

**建议用例**：支付 → 退款成功 → 查询 Dashboard，断言销售额是否应扣减。

**关联**：`CONFLICT-008`。

## R-09 库存状态“缺货”分支不可达

**观察**：后台库存列表用 `stock <= 5 ? 低库存预警 : (stock > 0 ? 正常 : 缺货)`，库存 0 会先命中“低库存预警”，永远显示不了“缺货”。

**证据**：`admin.py#L285`。

**影响**：后台库存状态展示与预期不符；UI 断言需按当前实现。

**建议用例**：库存 0 的无线鼠标，查询 `/api/admin/inventory`，断言状态文本。

**关联**：`AUTO-LIMITATIONS`。

## R-10 商品编辑全量替换 SKU

**观察**：`_apply_skus` 删除商品全部旧 SKU 后重建，SKU ID 变化；购物车/订单明细可能引用旧 ID。

**证据**：`products.py#L125-L143`、`products.py#L169-L191`。

**影响**：更新商品后购物车项可能失效；退款恢复库存可能找不到 SKU；自动化用例若缓存 SKU ID 会失败。

**建议用例**：加购 → 管理员编辑商品 SKU → 查询购物车/下单（跨模块，需确认）。

**关联**：`AUTO-LIMITATIONS`、`DATA-ORDER-001`。

## R-11 发货接受空物流信息

**观察**：`ShipRequest.company`/`tracking_number` 是必填 `str`，但无 `min_length`，传空字符串可发货成功；前端 `AdminOrders.tsx#L38、L107-L108` 有必填校验，风险仅在 API 层。

**证据**：`schemas.py#L177-L181`、`admin.py#L156-L178`。

**影响**：直连 API 可产生无物流信息的“已发货”订单，物流查询/签收断言失去意义。

**建议用例**：API 传 `company=""` 或 `tracking_number=""`，期望 400/422（当前实际 200，属已确认缺陷，Q-11）。

**关联**：`RULE-ORDER-010`、`API-ORDER-006`、`CONFLICT-011`。

# 3. 对评审的影响

- 以上风险可以帮助评审发现“用例遗漏的异常路径”，但不能直接判定用例错误；
- 评审意见引用时，应标记 `EXP-ORDER-001` 为 `E4`，并同时引用对应 `RULE-*` 或代码位置；
- 若要把某条风险升级为业务规则，必须先由业务负责人确认并新建/更新 `RULE-*`。

# 4. 不应得出的结论

- 不能因为 R-01 就说“产品要求允许超卖”；
- 不能因为 R-04 就说“优惠券可以无限领取是正确规则”；
- 不能因为 R-07 就说“单规格商品本来就不该支持加购”；
- 不能把本文件的任何一条当作 `E1` 业务事实。

# 5. 待确认

- 超卖是否为已知限制？是否在 Roadmap 中修复？
- 下单后购物车是否应清空？
- 退款拒绝后应恢复哪个状态？
- 多支付记录时订单详情应展示哪一条？
- 券 `total_quantity` 到底限制“发放”还是“使用”？
- 单规格商品无法加购是否为已知缺陷？修复计划？


# 本次授权技术复核适用性

保留 E4 风险线索级别；修正无排序支付选择与 sessionStorage 刷新语义，不据此断言目标行为已实现。

本次结论基于冻结快照与既有决策，当前实现中的限制不代表目标规格；已决策但未实施的项目仍按治理台账单独跟踪。复核者为用户授权的 AI 代理，非新增人工签署。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：修改后通过
- **审核人**：平台设计者（产品负责人）
- **审核日期**：2026-11-11
- **审核意见**：R-01~R-10 全部证据行号核对无误（orders.py:45-59,116-170,161-166；payments.py:15-36,50-74,92-102；coupons.py:40-88；refunds.py:14-41；admin.py:28-33,226-245,285；models.py:192；common.py:164-174；products.py:125-143,169-191），且未把缺陷包装成规则。缺陷：遗漏已确认的"发货接受空物流信息"风险（schemas.py:178-180 无 min_length，admin.py:156-178 不拒空值）。
- **复核备注**：修订要求：新增 R-11 发货空值风险；R-06 按设计者实测升级为确定性结论（Order.payment 恒返回第一条 FAILED 并抛 SAWarning，SQLAlchemy 2.0.36）；§5"待确认"按本轮 Q-02/Q-04/Q-06 决策改写为已确认口径。
- **回写说明**：2026-11-12 已按复核意见回写；仍为 in_review，待复审后置 approved。
