# MiniShop 项目知识库入口

> 项目标识：`minishop`
> 产品版本：`1.0.0`
> 知识快照：来源 2026-11-11；复核回写 2026-11-12
> 状态：**21 份 approved / 16 份 in_review（待复审）**
> 试点模块：`order`

## 1. 项目一句话说明

MiniShop 是一个用于测试平台联调和用例评审的轻量级综合电商 Demo，覆盖“注册登录 → 浏览商品 → 购物车 → 地址/优惠券 → 下单 → 模拟支付 → 发货 → 确认收货 → 评价 → 退款”的完整闭环。

## 2. 本知识库回答什么问题

本批知识用于支撑 **交易域（order）测试用例评审**，可以回答：

- 下单前必须满足哪些前置条件？
- 金额、优惠、库存由谁计算，依据是什么？
- 订单有哪些状态，允许哪些转换？
- 支付成功/失败、重复支付分别会发生什么？
- 取消、发货、确认收货的约束是什么？
- 测试数据如何准备，结果如何观察和断言？
- 哪些行为当前**没有**实现，不能按常识假设？

## 3. 知识地图

| 评审维度 | 首选知识 | 文件 |
|---|---|---|
| 业务意图与规则正确性 | 需求 + 业务规则 | `requirements/order/`、`rules/order/` |
| 前置条件充分性 | 角色权限 + 规则 + 状态机 | `project/roles_and_permissions.md`、`rules/order/`、`workflows/order/STATE-ORDER-001.md` |
| 步骤与流程一致性 | 主流程 + 接口 | `workflows/order/FLOW-ORDER-001.md`、`interfaces/order/` |
| 预期结果可判定性 | 业务规则 + 接口响应 + 数据表 | `rules/order/`、`interfaces/order/` |
| 测试数据完整性 | 测试数据策略 + 种子数据 | `testing/test_data_strategy.md`、`interfaces/order/DATA-ORDER-001.md` |
| 边界与异常覆盖 | 规则边界 + 状态机 + 风险线索 | `rules/order/`、`WORKFLOW`、`expert_knowledge/order/EXP-ORDER-001.md` |
| 自动化可行性 | 自动化能力 + 接口 | `automation/`、`interfaces/order/` |

## 4. 覆盖边界

### 已覆盖

- `order` 模块的预览、创建、支付、发货、确认收货、取消；
- 订单相关的金额、优惠券、地址、SKU/库存、权限、状态约束；
- 支撑交易流程的登录、商品查询、购物车、地址、优惠券接口的最小约束（见 `DATA-ORDER-001` 的测试数据准备章节）；
- 项目测试规范、环境、数据策略、自动化限制；
- 知识缺口、冲突与发布治理。

### 未覆盖

- `after_sales`（退款）完整规则；
- `review`（评价）完整规则；
- `admin` 后台除发货外的完整规则；
- 商品、分类、库存、优惠券的后台维护规则；
- 站内消息、收藏；
- 非功能需求（性能、安全、可用性）。

未覆盖内容不得从本批文档推断。相关缺口已登记在 `_governance/knowledge_gaps.yaml`。

## 5. 使用顺序建议

1. 先读 `project/overview.md` 与 `project/modules.yaml` 确认范围。
2. 读 `workflows/order/STATE-ORDER-001.md` 建立状态全局观。
3. 按评审用例涉及的主题检索对应 `RULE-ORDER-*`。
4. 需要验证方式时读 `interfaces/order/API-ORDER-*` 与 `DATA-ORDER-001`。
5. 设计测试数据时读 `testing/test_data_strategy.md`。
6. 引用结论时同时给出 `knowledge_id`、`source_ref` 与证据等级。

## 6. 证据与审核状态

- 2026-11-12 已应用人工复核：**21 份 `approved`、16 份 `in_review`**；16 份已完成修改但仍待复审，复审前不进入正式评审候选集；
- 所有文档填写了 `reviewer`/`reviewed_at`，并追加“复核记录”；
- 业务规则来自代码实际行为，`evidence_level: E2`；
- 测试/自动化规范为 `E3`，风险线索为 `E4`；
- 正式 PRD 待核验；GitHub 源码已绑定完整提交，原数据库和全部 80 项资料已有受控快照；原始审核工作簿已取得，77 行业务数据与既有记录完全一致。

## 7. 交付与自检

本批共 37 份知识文档，另有 15 项知识缺口、10 项冲突、15 项待确认。

| 材料 | 位置 |
|---|---|
| 项目资料盘点 | [`../_delivery/01_source_inventory.md`](../_delivery/01_source_inventory.md) |
| 知识提取映射 | [`../_delivery/02_extraction_matrix.md`](../_delivery/02_extraction_matrix.md) |
| 质量自检报告 | [`../_delivery/03_quality_report.md`](../_delivery/03_quality_report.md) |
| 待人工确认 | [`../_delivery/04_pending_confirmation.md`](../_delivery/04_pending_confirmation.md) |
| 建设总结 | [`../_delivery/05_build_summary.md`](../_delivery/05_build_summary.md) |
| 最终报告 | [`../_delivery/06_final_report.md`](../_delivery/06_final_report.md) |
| 独立审核报告 | [`../_delivery/07_audit_report_2026-11-12.md`](../_delivery/07_audit_report_2026-11-12.md) |
| 人工复核回写报告 | [`../_delivery/08_review_application_2026-11-12.md`](../_delivery/08_review_application_2026-11-12.md) |
| 当前整改与验证 | [`../_delivery/09_contract_remediation_2026-11-12.md`](../_delivery/09_contract_remediation_2026-11-12.md) |
| 知识缺口 | [`_governance/knowledge_gaps.yaml`](_governance/knowledge_gaps.yaml) |
| 知识冲突 | [`_governance/conflicts.yaml`](_governance/conflicts.yaml) |
| 待确认（机读） | [`_governance/pending_confirmation.yaml`](_governance/pending_confirmation.yaml) |
| 发布记录 | [`_governance/release_notes.md`](_governance/release_notes.md) |

自检结果：37 份文档、原快照 86 个行号锚点；旧检查的零错误/零警告不代表发布验收完成。`approved=21`、`in_review=16`；原始 80 项来源及数据库已完整归档，离线候选为 21 份，16 份待复审文档被排除。正式检索仍未启用，当前验证见 `../_delivery/09_contract_remediation_2026-11-12.md`。
