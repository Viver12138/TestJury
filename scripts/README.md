# scripts · 契约检查与规范工具

> 本目录放**设计契约的自动检查**与规范参考实现。除标注"需要 `DATABASE_URL`"的运维脚本外，不依赖数据库、网络或真实模型，可在 CI 与本地离线运行。
> 设计说明见 `docs/28`；检查项与 M0 验收的对应关系见 `design/m0_acceptance.yaml`。

## 依赖

`python>=3.11`、`pyyaml`、`jsonschema`（仅 Rubric Schema 校验需要）。无其他运行时依赖。

## 入口

```bash
python scripts/check_contracts.py            # 全部检查（CI 唯一入口）
python scripts/check_contracts.py --list     # 列出检查模块
python scripts/check_contracts.py --only docs,rubric
python scripts/check_contracts.py --json     # 机器可读输出
```

退出码：`0` 全部通过；`1` 存在错误。环境变量 `TJ_REPO_ROOT` 可把检查指向仓库副本（变异测试用）。

## 脚本

| 脚本 | 作用 | 失败时定位信息 |
|---|---|---|
| `contract_lib.py` | 共享工具：路径、YAML/JSON 读取、Markdown 表格解析、发现项与统一输出 | — |
| `check_contracts.py` | 聚合入口；按模块运行并汇总，支持 `--list/--only/--json` | 检查项 + 文件:行 |
| `check_docs.py` | 文档索引、版本头、枚举（docs/17 ↔ 报告 Schema）、幂等口径、废弃语义、决策索引、README 决策表、文档引用、Schema 冻结、脚本索引 | 文件 + 枚举/字段 + 期望与实际 |
| `check_rubric.py` | Rubric Schema、业务约束（checkpoint 唯一、阈值顺序、票数门槛）、冻结副本、docs/05 Prompt 引用、报告 Schema 枚举一致 | Rubric 路径/规则 ID |
| `check_verdict_cases.py` | `design/verdict_cases.yaml` 结构、规则覆盖、参考判定器一致、I1–I8 属性抽样 | 用例 ID + 规则 ID + 期望/实际 |
| `check_m0_acceptance.py` | `design/m0_acceptance.yaml` 结构、M0 十项与 P0/BIZ 项覆盖、追踪字段、CI Job、docs/08 一致性 | 用例 ID + 缺失字段 |
| `check_execution_plan.py` | `design/execution_plan.yaml` 与模型准入/实验协议/KB 试点/复核责任表的结构、状态与证据完整性 | 待决项/验证项 ID + 缺失字段 |
| `check_kb.py` | 知识内容兼容、严格 YAML、来源版本/哈希/行号、治理四维状态、审核后变更；`--release` 验证发布仍被阻止 | 文档/来源/治理 ID + 具体原因 |
| `build_kb_candidate.py` | 显式选择评审基线，生成可检查的离线候选片段；排除待复审和来源缺失文档，不调用模型或发布 | 文档 ID + 来源/结构问题 |
| `check_execution_gate.py` | 阶段执行门禁：owner、证据文件、验收人/时间、协议签署、S1–S4 出口（手动/阶段验收运行） | 项 ID + 缺失证据/出口 |
| `verdict_reference.py` | `docs/12` 真值表的**规范参考实现**（纯函数，非生产代码）；供用例一致性与属性测试使用 | 抛 `VerdictInputError` 时指示字段 |
| `rebuild_projection.py` | 运维脚本：从 `report_json` 重建 `issues` 投影并校验；支持 `--review/--all/--check`（需要 `DATABASE_URL`） | 评审 ID + 不一致字段 |
| `check_consistency.py` | 运维脚本：报告/投影、人工决定、候选映射、附件绑定一致性检查（需要 `DATABASE_URL`） | 评审 ID + 具体不一致项 |
| `check_model_connectivity.py` | 模型连通性冒烟：按 models.yaml 对真实供应商发最小 JSON 请求，记录延迟/token/JSON 能力；不打印密钥（需要供应商 Key） | 角色 + 错误码/状态码 |
| `adjudicate.py` | 人工裁决工作台：录入 issue 级 validity/severity/correction 与用例结论，追加 history；不代替人工签名 | 用例/候选 ID + 非法字段 |
| `adjudication_sheet.py` | 生成带下拉选项的 `adjudication.xlsx`（含原始用例快照），回收为 CSV；支持 `--root` 分别处理 UI/功能工作台 | 已填/未填、非法下拉值、重复导入 |

## 输出格式

```
[ERROR] docs | docs/19-API错误码与契约.md | REVIEW_IN_PROGRESS | 错误码表缺少 409 REVIEW_IN_PROGRESS
[ERROR] verdict-cases | design/verdict_cases.yaml | VC-014.ai_verdict | 期望 'need_human'，实际 'blocked'
```

要求：每条错误包含检查项、文件（可带行号）、规则/字段、期望与实际。只输出"检查失败"视为实现缺陷。

## 检查边界

- 设计阶段能查的：文档、枚举文本、YAML/JSON Schema、决策索引、用例完整性、参考判定器。
- 需要实现后才能查的：Python Enum 实际值、数据库 DDL/CHECK、API 响应示例、`verdict.py` 与用例一致、RULE-ID 内容唯一性。这些在 `design/m0_acceptance.yaml` 中列为 M0 用例（如 ACC-M0-005、ACC-M0-004、ACC-M0-011），不要在实现前宣称已通过。
- `verdict_reference.py` 只用于对照，**不得被生产代码引用**；生产唯一入口是 `app/pipeline/verdict.py`。
# 知识接入与隔离验收补充

- `prepare_knowledge_release.py`：构建不可变知识版本并运行检索黄金集，保存验收证据；不自动启用。
- `evaluate_review_gold.py`：执行真实模型或 Mock 黄金用例评审；区分流程验证与效果验证。
- `verify_isolated.py`：新建独立数据库运行测试并清理，仅删除本脚本创建的临时库。
- `benchmark_queue.py`：需要可创建临时库的 PostgreSQL 连接（`VERIFY_ADMIN_DATABASE_URL`）；以 Mock 模型测量服务层提交与队列并发，保存任务数、耗时及清理证据，不包含 HTTP、真实知识检索或供应商耗时。
- `serve_local.py`：升级数据库结构、加载验收过的本地知识版本并启动 Excel 上传网页；默认仅本机免凭证，可用 `LOCAL_REQUIRE_API_KEY=true` 恢复凭证要求；不清空数据，保留已有启用版本。
- `verify_minishop_gold.py`：在临时 SQLite 数据库验证归档 MiniShop 的 15 个黄金集业务事实，认证使用测试身份，不连接原项目数据库；支持 `--dataset` 与 `--output`，修订数据集时另存证据，不覆盖旧版记录。
- `compare_order_knowledge.py`：读取冻结的下单缺陷用例，对同一输入执行知识库启用/禁用的成对双模型评审；`--mode mock` 验证流程，`--mode live` 需要供应商密钥并产生费用。仅使用独立临时 PostgreSQL 数据库，正常完成后清理；中断保留数据库供诊断，不影响本地应用库。
- `export_order_comparison.py`：从已完成的真实成对评审与逐条 AI 复核记录生成对比 Excel，验证原始报告哈希、输入一致性与导出内容；标明评审不完整、重复项和样本限制，不调用模型。
