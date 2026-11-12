# TestJury 项目知识库数据（MiniShop）

> 依据：`TestJury_项目知识库数据规范_v1.0.md`（2026-11-11）
> 项目标识：`minishop`
> 知识快照：来源 2026-11-11；复核回写 2026-11-12
> 当前状态：**24 份 approved / 13 份 in_review（修改后待复审）**；13 份复审前不进入正式评审候选集

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
- **规模**：37 份知识文档；人工复核已回写，24 份 `approved`、13 份 `in_review`（待复审）。

未纳入本批的模块（`catalog`、`auth`、`after_sales`、`review`、`admin` 等）已在 `minishop/project/modules.yaml` 和 `minishop/_governance/knowledge_gaps.yaml` 中登记，不得用本批文档推断其完整规则。

## 3. 数据来源与证据策略

本批资料没有可用的正式 PRD 或需求系统，内容来自以下可核对来源：

| 来源 | 用途 |
|---|---|
| `Minishop/README.md` | 产品定位、功能清单、种子数据、业务规则声明 |
| `Minishop/backend/app/**` | 实际实现、状态码、字段、状态转换、错误消息 |
| `Minishop/frontend/src/**` | 页面流程、前端约束与已知 UI 缺陷 |
| `Minishop/e2e_test.py` | 已有端到端行为验证（48 项通过） |

因此：

- 业务规则以**代码实际行为**为准，README 只作为意图声明；两者不一致时登记到 `conflicts.yaml`。
- 2026-11-12 已应用人工复核：**24 份 `approved`、13 份 `in_review`（修改已回写，待复审）**；所有文档均填写 `reviewer`/`reviewed_at`。复审前，13 份文档仍不进入正式评审候选集。
- 本工作区**没有 `.git` 仓库**，无法提供 `git_commit`。发布记录中已登记该限制；审核通过后应以实际提交号补录。

## 4. 审核与发布

进入正式评审前必须完成：

1. 业务负责人逐份确认 `rules/order/RULE-ORDER-*.md` 与 `requirements/order/REQ-ORDER-*.md`。
2. 测试负责人确认 `testing/` 与 `automation/` 中的验证方式。
3. 在每份文档 YAML Front Matter 中填写 `reviewer`、`reviewed_at`，并将 `status` 改为 `approved`。
4. 处理 `_governance/conflicts.yaml` 中所有 `open` 项，不能处理的影响范围要写入 `knowledge_gaps.yaml`。
5. 在 `_governance/release_notes.md` 中登记发布版本、审核人和 Git commit（如有）。

> 审核前，TestJury 的 `status=approved` 检索过滤会排除未批准文档；当前 24 份已批准、13 份仍会被排除，这是预期行为。

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
| 知识缺口 | [`minishop/_governance/knowledge_gaps.yaml`](minishop/_governance/knowledge_gaps.yaml) |
| 知识冲突 | [`minishop/_governance/conflicts.yaml`](minishop/_governance/conflicts.yaml) |

### 自检结论

- 37 份知识文档、86 个行号锚点：**0 错误、0 警告、0 来源漂移**；
- `approved` **24**，`in_review` **13**（修改已回写，待复审）；
- 15 个待确认问题全部答复，10 个冲突完成知识级裁决，15 个缺口状态更新；
- 当前可支撑 24 份已批准文档的评审检索；整体正式评审仍受 13 份复审、代码/配置修复和 PRD/用例缺口阻塞。

### 一句话结论

> 本批交付的是一个可审核、可追溯、可扩展的候选知识库；不是已发布知识库，也没有用推断填补任何业务空白。
