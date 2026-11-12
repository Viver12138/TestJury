# 交付物：待人工确认清单

> **状态更新（2026-11-12）**：本清单 15 项已由《MiniShop_知识库人工确认清单_复核修正版.xlsx》全部答复并回写，逐项结论见 `minishop/_governance/pending_confirmation.yaml`；本文件保留最初的待确认视图作为历史记录。

> 来源：`minishop/_governance/pending_confirmation.yaml`
> 共 15 项，其中 **10 项阻塞**正式评审。
> 在确认前，相关知识结论必须降级为“待确认”，不得写成强制业务事实。

## 1. 阻塞项（blocking=true）

| ID | 主题 | 需要确认的问题 | 关联 |
|---|---|---|---|
| Q-01 | 立即购买的定义 | “立即购买”应直接结算，还是加购后跳购物车即可？ | `CONFLICT-001`、`REQ-ORDER-001` |
| Q-02 | 库存预占与超卖 | 下单是否应锁定库存？支付时库存不足应失败还是继续？ | `CONFLICT-002`、`GAP-012` |
| Q-03 | 下单后购物车 | 下单成功后是否应清空已购买项？ | `RULE-ORDER-006` |
| Q-04 | 退款拒绝后的状态 | 应回到 `PAID`、`SHIPPED` 还是 `COMPLETED`？ | `CONFLICT-010`、`STATE-ORDER-001` |
| Q-05 | 多支付记录的详情展示 | 失败重试成功后，详情应展示哪一条支付记录？ | `CONFLICT-007`、`API-ORDER-003` |
| Q-06 | 券 `total_quantity` 语义 | 限制“发放总量”还是“使用总量”？ | `CONFLICT-006`、`RULE-ORDER-004` |
| Q-08 | `PENDING_SHIPMENT` 状态 | 启用为“待发货”，还是删除？当前从未赋值。 | `CONFLICT-004`、`STATE-ORDER-001` |
| Q-10 | 单规格商品无法加购 | 是否为已知缺陷？修复计划？ | `CONFLICT-009`、`EXP-ORDER-001` |
| Q-12 | 订单超时关闭 | 是否需要超时自动取消？时长？ | `GAP-012`、`REQ-ORDER-004` |
| Q-15 | 版本发布信息 | 1.0.0 发布日期、变更、Git commit？ | `GAP-006`、`GAP-015` |

## 2. 非阻塞项（blocking=false）

| ID | 主题 | 需要确认的问题 | 关联 |
|---|---|---|---|
| Q-07 | 券 `start_time` | 未生效券是否允许领取/使用？当前只校验 `end_time`。 | `GAP-013` |
| Q-09 | Dashboard 销售额口径 | 销售额是否扣除已退款订单？ | `CONFLICT-008` |
| Q-11 | 空物流信息 | 空公司/空运单号是否算有效发货？当前接受。 | `RULE-ORDER-010` |
| Q-13 | Docker `seed_media` | 补目录还是删除 COPY/挂载？ | `CONFLICT-005` |
| Q-14 | 商品图 SVG | 改 URL 编码、Base64，还是静态文件？ | `AUTO-LIMITATIONS` |

## 3. 确认后的动作

1. 回答 `blocking=true` 的问题；
2. 对每个回答，更新对应 `RULE-*` / `REQ-*` / `STATE-*` 文档；
3. 若行为变化，创建新知识版本并记录 `supersedes`；
4. 在 `conflicts.yaml` 中把对应冲突置为 `resolved`，填写 `resolution`/`resolved_at`；
5. 在 `knowledge_gaps.yaml` 中关闭已解决的缺口；
6. 由业务负责人填写 `reviewer`/`reviewed_at`，再把 `status` 改为 `approved`；
7. 更新 `release_notes.md`。

> 未经回答的问题，不得用“行业惯例”或“常见电商做法”补齐。
