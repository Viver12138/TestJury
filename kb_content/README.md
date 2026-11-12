# TestJury 项目知识库数据（MiniShop）

> 依据：`TestJury_项目知识库数据规范_v1.0.md`（2026-11-11）
> 项目标识：`minishop`
> 知识快照：来源 2026-11-11；复核回写 2026-11-12
> 当前状态：**21 份 approved / 16 份 in_review（修改后待复审）**；16 份复审前不进入正式评审候选集

本目录是 MiniShop 综合电商测试 Demo 的项目知识库事实源，按 TestJury 规范组织。目录内只存放**评审依据**，不存放待评审用例、人工评审黄金集或模型输出。

## 1. 目录导航

```text
kb_content/
├── README.md                     # 本文件：交付说明
├── _global/                      # 全局知识命名空间（本批不复制，见其 README）
├── _delivery/                    # 盘点、提取映射、质量自检、待确认、最终报告
└── minishop/                     # 项目知识命名空间
    ├── README.md                 # 项目知识库入口与覆盖范围
    ├── project/                  # 项目级：概览、版本、平台、角色、模块、环境
    ├── requirements/order/       # 试点模块需求：订单预览/创建/支付/发货/取消
    ├── rules/order/              # 试点模块核心业务规则（RULE-ORDER-001~011）
    ├── workflows/order/          # 下单主流程与订单状态机
    ├── interfaces/order/         # 订单/支付/发货接口与数据约束
    ├── testing/                  # 项目测试规范、测试环境、测试数据策略
    ├── automation/               # 自动化能力、定位与断言、限制
    ├── glossary/                 # 业务术语
    ├── expert_knowledge/order/   # 代码走查得到的交易域风险线索（E4）
    └── _governance/             # 知识缺口、冲突、发布记录
```

## 2. 本批覆盖范围

本批按规范“小步建设”原则，选择一个模块做端到端试点：

- **试点模块：`order`（交易域）**，覆盖订单预览、创建、支付、发货、确认收货、取消，以及支撑这些流程所必需的购物车、地址、优惠券前置约束。
- **项目级资料**：概览、版本、平台、角色权限、模块清单、环境。
- **测试与自动化**：项目测试规范、环境说明、测试数据策略、自动化能力与限制。
- **治理**：15 项知识缺口、10 项冲突、15 项待确认、候选发布记录。
- **规模**：37 份知识文档；人工复核已回写，21 份 `approved`、16 份 `in_review`（待复审）。

未纳入本批的模块（`catalog`、`auth`、`after_sales`、`review`、`admin` 等）已在 `minishop/project/modules.yaml` 和 `minishop/_governance/knowledge_gaps.yaml` 中登记，不得用本批文档推断其完整规则。

## 3. 数据来源与证据策略

本批资料没有可用的正式 PRD 或需求系统，内容来自以下可核对来源：

| 来源 | 用途 |
|---|---|
| `Minishop/README.md` | 产品定位、功能清单、种子数据、业务规则声明 |
| `Minishop/backend/app/**` | 实际实现、状态码、字段、状态转换、错误消息 |
| `Minishop/frontend/src/**` | 页面流程、前端约束与已知 UI 缺陷 |
| `Minishop/e2e_test.py` | 历史独立库曾报告 48 项通过；当前快照受种子券过期影响，不能充当已验收回归基线 |

因此：

- 基线必须显式选择并冻结：当前实现绑定源码 commit，目标规格绑定人工决策材料 SHA-256；代码缺陷不能覆盖已确认目标规则。
- 2026-11-12 已应用人工复核：**21 份 `approved`、16 份 `in_review`（修改已回写，待复审）**；所有文档均填写 `reviewer`/`reviewed_at`。复审前，16 份文档仍不进入正式评审候选集。
- MiniShop 已绑定源码仓库及完整提交，详见 `_delivery/source_binding.yaml`；Git 来源中 78 项匹配，忽略配置变化、数据库未入 Git；原项目 80 项文件已全部按旧哈希取回并归档，包括原数据库。
- 原人工复核工作簿和 77 行逐项比对结果已保存于 `evidence/M2/manual_review/`，内容与原提取记录一致；这不会自动批准本轮新修改的正文。

## 4. 审核与发布

进入正式评审前必须完成：

1. 业务负责人逐份确认 `rules/order/RULE-ORDER-*.md` 与 `requirements/order/REQ-ORDER-*.md`。
2. 测试负责人确认 `testing/` 与 `automation/` 中的验证方式。
3. 在每份文档 YAML Front Matter 中填写 `reviewer`、`reviewed_at`，并将 `status` 改为 `approved`。
4. 分别检查台账的人工决策、文档、实现和验证四维状态；不能处理的影响范围写入 `knowledge_gaps.yaml`。
5. 完成正式构建、检索与评审验收，并按权限发布；在 `_governance/release_notes.md` 中登记版本、审核人和来源提交。

> 内容 approved 只映射为平台 reviewed。正式检索还需 published + active 构建；当前运行时仍为 kb-none，未加载本批内容。

## 5. 不包含的内容

按规范第 2.5 节，以下内容不在本目录：

- 待评审测试用例；
- 人工标注的评审黄金集与检索黄金集；
- 模型生成的评审意见；
- 未经审核的会议记录或聊天内容。

MiniShop 的演示账号（`user/123456`、`admin/admin123`）是项目公开种子数据，不属于真实凭据。

## 6. 交付物与自检结果

| 交付物 | 文件 |
|---|---|
| 项目资料清单 | [`_delivery/01_source_inventory.md`](_delivery/01_source_inventory.md)、[`_delivery/source_inventory.yaml`](_delivery/source_inventory.yaml) |
| 知识提取映射 | [`_delivery/02_extraction_matrix.md`](_delivery/02_extraction_matrix.md) |
| 知识质量自检 | [`_delivery/03_quality_report.md`](_delivery/03_quality_report.md)、[`_delivery/validation_result.json`](_delivery/validation_result.json) |
| 待人工确认 | [`_delivery/04_pending_confirmation.md`](_delivery/04_pending_confirmation.md) |
| 建设总结 | [`_delivery/05_build_summary.md`](_delivery/05_build_summary.md) |
| 最终报告 | [`_delivery/06_final_report.md`](_delivery/06_final_report.md) |
| 独立审核报告 | [`_delivery/07_audit_report_2026-11-12.md`](_delivery/07_audit_report_2026-11-12.md) |
| 人工复核回写报告 | [`_delivery/08_review_application_2026-11-12.md`](_delivery/08_review_application_2026-11-12.md) |
| 当前整改与验证 | [`_delivery/09_contract_remediation_2026-11-12.md`](_delivery/09_contract_remediation_2026-11-12.md) |
| 原始来源及工作簿证据 | [`../evidence/M2/README.md`](../evidence/M2/README.md) |
| 知识缺口 | [`minishop/_governance/knowledge_gaps.yaml`](minishop/_governance/knowledge_gaps.yaml) |
| 知识冲突 | [`minishop/_governance/conflicts.yaml`](minishop/_governance/conflicts.yaml) |

### 自检结论

- 37 份知识文档、86 个行号锚点：旧检查曾报告 0 错误/0 警告；当前检查和限制见 `09_contract_remediation_2026-11-12.md`；
- `approved` **21**，`in_review` **16**（修改已回写，待复审）；
- 15 个待确认问题全部答复，10 个冲突完成知识级裁决，15 个缺口状态更新；
- 当前仅支持离线候选解析与人工检查；正式检索仍受复审、来源、实现修复、PRD/黄金集和发布链路阻塞。

### 一句话结论

> 本批交付的是一个可审核、可追溯、可扩展的候选知识库；不是已发布知识库，也没有用推断填补任何业务空白。
