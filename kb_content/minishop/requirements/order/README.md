# 订单模块需求导航（order）

本目录是 `order` 试点模块的需求与验收标准。

## 文档清单

| ID | 标题 | 覆盖 |
|---|---|---|
| `REQ-ORDER-001` | 订单预览与创建 | 服务端重算、库存/优惠券/地址校验、订单快照 |
| `REQ-ORDER-002` | 模拟支付 | 创建支付单、支付成功/失败、重复支付保护、库存扣减 |
| `REQ-ORDER-003` | 发货与确认收货 | 管理员发货、物流单、用户确认收货 |
| `REQ-ORDER-004` | 订单取消 | 待支付取消、优惠券归还 |

## 范围说明

- 本模块覆盖订单从“预览”到“完成/取消”的主链路。
- 支付是订单状态推进的一部分，接口在 `/api/payments`，本模块一并覆盖。
- 发货接口在 `/api/admin/orders/{id}/ship`，属于管理员能力，但服务于订单状态机，本模块一并覆盖。
- 退款、评价不在本模块：退款见 `after_sales`（本批未覆盖），评价见 `review`（本批未覆盖）；本模块只在状态机中登记它们对订单状态的影响。

## 需求来源说明

仓库没有正式 PRD。本目录需求由 `Minishop/README.md` 的功能声明与 `Minishop/backend/app/api/` 的实际实现整理而来：

- 与 README 一致的声明，作为需求意图；
- README 未写但代码实现的约束，作为当前功能事实；
- 两者冲突或代码未实现的，写入“明确不支持的行为”或“未决问题”，不自行补造。

因此所有需求文档的 `evidence_level` 为 `E2`，`status` 为 `in_review`，需业务负责人确认后才能作为正式评审依据。

## 阅读顺序

1. `REQ-ORDER-001` → `REQ-ORDER-002` → `REQ-ORDER-003` → `REQ-ORDER-004`
2. 对应规则：`rules/order/RULE-ORDER-001` ~ `011`
3. 流程与状态：`workflows/order/FLOW-ORDER-001`、`STATE-ORDER-001`
4. 接口与数据：`interfaces/order/API-ORDER-001` ~ `006`、`DATA-ORDER-001`
