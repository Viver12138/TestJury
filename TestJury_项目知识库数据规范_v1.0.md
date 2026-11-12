# TestJury 项目知识库数据规范

> 文档类型：设计规范  
> 适用范围：TestJury 接入任意新测试项目时，项目知识资料的组织、编写、审核、发布、检索与评审引用  
> 状态：建议稿，待项目级确认  
> 版本：v1.0  
> 日期：2026-11-11

> 2026-11-12 兼容补充：本规范描述内容侧格式；平台字段、生命周期和发布权限以 `docs/17`、`docs/11` 为准。可执行映射见 `design/kb_contract.yaml`，实现与校验见 `app/knowledge/`、`scripts/check_kb.py`。本次补充不构成人工业务审核或正式发布。

---

## 1. 文档目的

本文定义 TestJury 项目知识库的数据规范，解决以下问题：

1. 新项目需要提供哪些知识资料，才能支撑测试用例评审。
2. 不同类型的知识资料应该如何组织、命名和编写。
3. 如何记录知识来源、适用范围、版本、有效期和审核状态。
4. 如何区分正式业务事实、需求描述、测试规范、历史经验和模型推断。
5. 如何避免过期、冲突、未经审核的知识影响评审结论。
6. 如何让检索结果可以定位回原始文件和具体内容。
7. 如何验收知识库是否真正提升了评审质量。

本文定义的是**知识数据层规范**，不规定具体向量数据库、Embedding 模型、Reranker 或检索框架的实现方式。

## 2. 设计原则

### 2.1 事实源与检索索引分离

- Git 仓库中的 Markdown、YAML、JSON 等受版本控制文件是知识事实源。
- PostgreSQL 等数据库只保存解析结果、检索索引和必要的运行元数据，不得成为唯一事实源。
- 删除或重建检索索引，不应导致原始知识丢失。
- 每次知识发布必须能够追溯到 Git commit 或等价的不可变版本标识。

### 2.2 项目隔离

- 每个项目拥有独立的知识命名空间。
- 不同项目的业务规则不得默认互相继承。
- 全局测试规范可以被多个项目引用，但必须明确标记为全局知识。
- 检索必须先限定项目范围，再进行模块、版本和知识类型过滤。
- 未明确允许共享的项目资料，不得进入其他项目的检索结果。

### 2.3 证据优先

- 评审结论必须区分“来源明确的事实”和“基于经验的推断”。
- 不能因为某条知识被检索到，就默认它权威、有效或适用于当前版本。
- 无法找到充分依据时，应输出知识缺口或降低结论强度，不得自行补造业务规则。

### 2.4 小步建设

- 不要求新项目一次性提交所有文档。
- 首批至少选择一个资料相对完整的功能模块进行端到端试点。
- 先确保关键规则可追溯、可检索、可引用，再扩展覆盖范围。
- 缺失资料应被显式登记，不得通过虚构内容填补。

### 2.5 知识与评审对象分离

以下内容必须分开管理：

| 数据 | 定位 | 是否默认进入项目事实知识库 |
|---|---|---|
| 需求、业务规则、流程、接口约束 | 评审依据 | 是 |
| 测试规范、自动化规范 | 评审标准依据 | 是，按全局或项目范围管理 |
| 待评审测试用例 | 评审对象 | 否 |
| 人工标注的评审黄金集 | 评测数据 | 否，独立管理 |
| 历史缺陷 | 历史证据/风险线索 | 经审核后可作为受限知识 |
| 模型生成的评审意见 | 模型输出 | 否 |
| 未经审核的会议记录、聊天内容 | 待整理材料 | 否，完成审核后再入库 |

## 3. 知识库内容分类

知识库分为项目知识和全局知识两大范围。

### 3.1 项目知识

| 类型编码 | 知识类型 | 内容范围 | 首批要求 |
|---|---|---|---|
| `PROJECT` | 项目基础信息 | 项目定位、版本、平台、角色、环境、模块 | 必需 |
| `REQUIREMENT` | 需求与功能说明 | PRD、功能规格、验收标准、需求变更 | 必需 |
| `BUSINESS_RULE` | 业务规则 | 前置条件、权限、数值、状态约束、异常规则 | 核心必需 |
| `WORKFLOW` | 业务流程与状态 | 正常流程、异常流程、状态机、跨模块交互 | 核心必需 |
| `INTERFACE` | 接口与数据约束 | API、字段、错误码、数据准备与查询方式 | 按评审范围要求 |
| `TEST_SPEC` | 项目测试约定 | 项目测试策略、测试环境、数据约定 | 必需或引用全局规范 |
| `AUTOMATION` | 自动化能力说明 | 框架、定位、断言、执行限制 | 进行自动化可行性评审时必需 |
| `GLOSSARY` | 术语 | 业务名词、缩写、状态术语 | 建议 |
| `HISTORICAL_BUG` | 历史缺陷 | 已发生缺陷、根因、修复版本、复发条件 | 后续补充 |
| `EXPERT_KNOWLEDGE` | 专家经验 | 经验总结、特殊约定、风险提示 | 后续补充 |

### 3.2 全局知识

全局知识适用于多个项目，但必须与项目事实隔离：

- 通用测试用例设计规范。
- 通用测试评审标准。
- 通用缺陷分类和风险分析方法。
- 自动化测试通用原则。
- TestJury 自身的评审 Rubric 和输出契约。

全局知识不能替代项目专属业务规则。例如，通用测试规范可以要求检查异常路径，但不能据此推断某个产品具体有哪些异常状态。

### 3.3 首批最小充分知识集

一个功能模块进入知识库试点评审前，至少应具备：

1. 项目和模块说明。
2. 当前有效的需求或功能规格。
3. 覆盖本次评审范围的核心业务规则。
4. 核心流程及关键状态定义。
5. 涉及执行和结果验证的接口、数据或可观察性说明。
6. 适用的测试规范（项目规范或明确引用的全局规范）。
7. 当前版本、平台和环境适用范围。

若某项资料客观不存在，应登记知识缺口，并说明哪些评审维度因此受限。不得为了满足清单而生成未经确认的业务事实。

## 4. 推荐目录结构

建议每个项目采用以下目录。目录是逻辑组织建议，实际仓库可根据现有路径调整，但必须保留同等的数据边界和元信息。

```text
kb_content/
├── _global/
│   ├── testing_standards/
│   ├── review_rubric/
│   ├── automation_principles/
│   └── glossary/
│
└── <project_id>/
    ├── README.md
    ├── project/
    │   ├── overview.md
    │   ├── versions.md
    │   ├── platforms.md
    │   ├── roles_and_permissions.md
    │   ├── modules.yaml
    │   └── environments.md
    │
    ├── requirements/
    │   └── <module_id>/
    │       ├── README.md
    │       └── REQ-<id>.md
    │
    ├── rules/
    │   └── <module_id>/
    │       ├── README.md
    │       └── RULE-<id>.md
    │
    ├── workflows/
    │   └── <module_id>/
    │       ├── FLOW-<id>.md
    │       └── STATE-<id>.md
    │
    ├── interfaces/
    │   └── <module_id>/
    │       ├── API-<id>.md
    │       └── DATA-<id>.md
    │
    ├── testing/
    │   ├── project_test_standards.md
    │   ├── test_environment.md
    │   └── test_data_strategy.md
    │
    ├── automation/
    │   ├── framework_overview.md
    │   ├── locator_and_assertion.md
    │   └── limitations.md
    │
    ├── glossary/
    │   └── terms.md
    │
    ├── historical_bugs/
    │   └── <module_id>/
    │       └── BUG-<id>.md
    │
    ├── expert_knowledge/
    │   └── <module_id>/
    │       └── EXP-<id>.md
    │
    └── _governance/
        ├── knowledge_gaps.yaml
        ├── conflicts.yaml
        └── release_notes.md
```

### 4.1 目录使用约束

- `<project_id>` 使用稳定、唯一、机器可读的项目标识，不使用随意变化的展示名称。
- `<module_id>` 必须来自项目模块清单。
- 每份独立规则、需求、流程和接口资料应有稳定 ID。
- `README.md` 用于解释目录内容和导航，不作为大量规则的唯一存放位置。
- `_governance` 用于记录知识缺口、冲突和发布信息，不替代正式知识正文。
- 原始附件可以单独存放，但必须有可追溯引用；不应把无法解析的附件当作已入库知识。

## 5. 通用元数据规范

每份可被检索和引用的知识文档，必须在正文顶部包含 YAML Front Matter。

### 5.1 必需字段

| 字段 | 类型 | 必需 | 说明 |
|---|---|---:|---|
| `id` | string | 是 | 全局稳定知识 ID |
| `title` | string | 是 | 文档标题 |
| `knowledge_type` | enum | 是 | 知识类型编码 |
| `project_id` | string | 项目知识必需 | 所属项目 |
| `module_id` | string/null | 否 | 所属模块；跨模块可为空 |
| `source_type` | enum | 是 | 原始来源类型 |
| `source_ref` | string | 是 | 原始文件、系统链接或资料编号 |
| `source_version` | string/null | 是 | 来源版本；未知时显式写 `null` |
| `product_version` | string/list | 是 | 适用产品版本或版本范围 |
| `platforms` | list | 是 | 适用平台；不区分时写 `["all"]` |
| `evidence_level` | enum | 是 | E1、E2、E3、E4 |
| `status` | enum | 是 | 生命周期状态 |
| `owner` | string | 是 | 负责维护的角色或团队 |
| `reviewer` | string/null | 是 | 审核者；未审核时为 `null` |
| `created_at` | date | 是 | 创建日期 |
| `updated_at` | date | 是 | 最近修改日期 |
| `effective_from` | date/null | 是 | 生效日期 |
| `effective_until` | date/null | 是 | 失效日期；长期有效写 `null` |
| `tags` | list | 是 | 检索标签，可为空列表 |

### 5.2 建议字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `related_ids` | list | 关联需求、规则、流程或接口 ID |
| `supersedes` | list | 被当前文档替代的知识 ID |
| `superseded_by` | list | 替代当前文档的知识 ID |
| `change_reason` | string | 本次变更原因 |
| `sensitivity` | enum | `public`、`internal`、`confidential`、`restricted` |
| `reviewed_at` | date/null | 最近审核日期 |
| `review_cycle_days` | integer/null | 建议复审周期 |
| `content_language` | string | 默认 `zh-CN` |
| `chunk_strategy` | enum | `section`、`paragraph`、`structured` |

### 5.3 示例

```yaml
---
id: RULE-ORDER-001
title: 未支付订单超时关闭规则
knowledge_type: BUSINESS_RULE
project_id: sample_project
module_id: order
source_type: PRD
source_ref: requirements/order/REQ-ORDER-003.md#timeout
source_version: "PRD-2.4"
product_version:
  - "2.4.x"
platforms:
  - all
evidence_level: E1
status: approved
owner: order_product_team
reviewer: product_owner
created_at: 2026-11-01
updated_at: 2026-11-10
effective_from: 2026-11-01
effective_until: null
reviewed_at: 2026-11-10
review_cycle_days: 90
tags:
  - order
  - timeout
  - state_transition
related_ids:
  - REQ-ORDER-003
  - STATE-ORDER-001
sensitivity: internal
content_language: zh-CN
---
```

以上仅为格式示例，业务内容和示例规则不能直接用于任何真实项目。

## 6. 枚举与标识规范

### 6.1 `knowledge_type`

允许值：

- `PROJECT`
- `REQUIREMENT`
- `BUSINESS_RULE`
- `WORKFLOW`
- `INTERFACE`
- `TEST_SPEC`
- `AUTOMATION`
- `GLOSSARY`
- `HISTORICAL_BUG`
- `EXPERT_KNOWLEDGE`

### 6.2 `source_type`

建议允许值：

- `PRD`
- `REQUIREMENT_SPEC`
- `DESIGN_DOC`
- `API_SPEC`
- `DATABASE_SCHEMA`
- `TEST_STANDARD`
- `AUTOMATION_DOC`
- `BUG_TRACKER`
- `MEETING_DECISION`
- `EXPERT_REVIEW`
- `OFFICIAL_WIKI`
- `OTHER`

`source_type` 表示来源类型，不代表来源权威等级。权威等级由 `evidence_level`、审核状态和适用范围共同决定。

### 6.3 `evidence_level`

沿用 TestJury 现有证据分级设计：

| 等级 | 定义 | 典型资料 | 可承担的判断 |
|---|---|---|---|
| E1 | 已审核、当前有效的权威业务事实 | 已确认业务规则、正式决策记录 | 可用于判断业务规则冲突 |
| E2 | 正式需求、设计和接口约束 | PRD、功能规格、API 文档 | 支撑功能意图、约束和可验证性判断 |
| E3 | 测试和质量规范 | 测试规范、自动化规范 | 支撑测试设计质量判断 |
| E4 | 经验、建议和通用推断 | 专家经验、通用测试知识 | 提供建议，不单独作为强制业务事实 |

注意：

1. E1–E4 是证据等级，不是文档格式或生命周期状态。
2. `approved` 不会自动把资料升级为 E1。
3. 历史缺陷默认不能直接作为 E1 业务规则。
4. 模型推断不得伪装成 E1 或 E2。
5. 当现有仓库对 E1–E4 有更具体定义时，以仓库正式定义为准；本节不得覆盖或削弱既有规则。

### 6.4 `status`

建议生命周期状态：

| 状态 | 含义 | 是否允许参与正式评审 |
|---|---|---|
| `draft` | 草稿 | 否 |
| `in_review` | 审核中 | 否 |
| `approved` | 内容审核通过，对应平台 `reviewed` | 仅为构建候选，不能直接进入正式检索 |
| `deprecated` | 已废弃 | 否 |
| `superseded` | 已被新版本替代 | 否 |
| `rejected` | 审核未通过 | 否 |
| `archived` | 已归档 | 否 |

只有 `approved` 且适用于当前项目、版本、平台和评审范围的知识，才可以进入构建候选集。正式证据还必须满足平台 `rule_status=published`、构建版本为 `active`、评审基线明确以及检索和评审验收通过。

### 6.5 与平台契约的兼容映射

内容侧字段 `id/module_id/knowledge_type` 分别映射到 `doc_id/module/doc_type`；同时提供新旧字段时，值不一致即报错。项目 ID 始终保留，ID 唯一性以 `(project_id, doc_id)` 为边界；项目级 `module_id=null` 只适用于本项目，不代表全局共享。

| 内容知识类型 | 平台 doc_type |
|---|---|
| `PROJECT` | `design` |
| `REQUIREMENT` | `requirement` |
| `BUSINESS_RULE` | `rule` |
| `WORKFLOW` | `flow` |
| `INTERFACE` | `design` |
| `TEST_SPEC` | `design` |
| `AUTOMATION` | `design` |
| `GLOSSARY` | `term` |
| `HISTORICAL_BUG` | `history_bug` |
| `EXPERT_KNOWLEDGE` | `design` |

类型映射不会提升原始证据等级；测试规范仍为 E3、经验推断仍为 E4。`draft/in_review → draft`，`approved → reviewed`，`deprecated/superseded/rejected/archived → deprecated`。解析器不产生 `published`；发布必须另经审核权限、构建、检索回归和版本切换流程。

### 6.6 治理状态与评审基线

台账分别记录 `decision_status`（pending/decided）、`documentation_status`（pending/synced/reviewed）、`implementation_status`（not_required/pending/implemented）和 `verification_status`（not_verified/passed/failed）。历史 `resolved/answered/blocking_resolved` 只保留为 `legacy_*` 记录，不授予发布或评审准入。

构建或评审必须显式选择 `current_implementation` 或 `target_specification`，冻结产品版本、来源引用和来源版本。当前实现以完整 Git SHA 绑定；目标规则以受控决策材料的 SHA-256 绑定。两者不能互相替代，基线变更必须生成新构建/任务版本。

来源使用仓库地址、完整 commit、仓库相对路径、SHA-256 与可选行号定位。快照与新仓库存在差异时，同时保留两份哈希，缺失的数据库或原审核材料不能用新生成数据冒充。已审核内容的哈希锁只记录已有审核快照；正文实质修改后应退回 `in_review`，新审核记录由有权人员补录。

## 7. 各类知识文档模板

### 7.1 项目概览模板

文件：`project/overview.md`

```markdown
---
id: PROJECT-OVERVIEW
title: 项目概览
knowledge_type: PROJECT
project_id: <project_id>
module_id: null
source_type: OTHER
source_ref: <source>
source_version: null
product_version: ["<version>"]
platforms: ["all"]
evidence_level: E2
status: draft
owner: <owner>
reviewer: null
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
effective_from: null
effective_until: null
tags: []
---

# 1. 产品定位

# 2. 目标用户与角色

# 3. 产品范围

# 4. 不在范围内的内容

# 5. 当前版本

# 6. 支持平台

# 7. 模块清单

# 8. 关键系统依赖

# 9. 环境差异

# 10. 相关资料
```

### 7.2 需求文档模板

文件：`requirements/<module_id>/REQ-<id>.md`

```markdown
---
id: REQ-<MODULE>-001
title: <需求标题>
knowledge_type: REQUIREMENT
project_id: <project_id>
module_id: <module_id>
source_type: PRD
source_ref: <原始需求链接或文件定位>
source_version: <需求版本>
product_version: ["<适用版本>"]
platforms: ["all"]
evidence_level: E2
status: draft
owner: <owner>
reviewer: null
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
effective_from: null
effective_until: null
tags: []
related_ids: []
---

# 1. 需求背景与目标

# 2. 用户与前置条件

# 3. 功能描述

# 4. 主成功场景

# 5. 异常与替代场景

# 6. 输入与输出

# 7. 业务约束

# 8. 验收标准

# 9. 明确不支持的行为

# 10. 未决问题
```

需求文档必须区分“原始需求明确规定的内容”和“整理者的解释”。未明确的内容放入“未决问题”，不得自行补齐。

### 7.3 业务规则模板

文件：`rules/<module_id>/RULE-<id>.md`

```markdown
---
id: RULE-<MODULE>-001
title: <规则标题>
knowledge_type: BUSINESS_RULE
project_id: <project_id>
module_id: <module_id>
source_type: <PRD|DESIGN_DOC|MEETING_DECISION|OTHER>
source_ref: <原始来源及定位>
source_version: <来源版本>
product_version: ["<适用版本>"]
platforms: ["all"]
evidence_level: E1
status: draft
owner: <owner>
reviewer: null
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
effective_from: null
effective_until: null
tags: []
related_ids: []
---

# 1. 规则陈述

使用可验证、无歧义的陈述表达规则。

# 2. 适用范围

# 3. 前置条件

# 4. 触发条件

# 5. 规则结果

# 6. 边界与例外

# 7. 反例或禁止行为

# 8. 验证方式

# 9. 来源依据

# 10. 未决问题
```

规则陈述应尽量做到“一条规则表达一个可独立验证的约束”。多个条件、例外和结果差异明显时，应拆分为多条规则。

### 7.4 业务流程模板

文件：`workflows/<module_id>/FLOW-<id>.md`

```markdown
---
id: FLOW-<MODULE>-001
title: <流程名称>
knowledge_type: WORKFLOW
project_id: <project_id>
module_id: <module_id>
source_type: DESIGN_DOC
source_ref: <来源及定位>
source_version: <来源版本>
product_version: ["<适用版本>"]
platforms: ["all"]
evidence_level: E2
status: draft
owner: <owner>
reviewer: null
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
effective_from: null
effective_until: null
tags: []
related_ids: []
---

# 1. 流程目标

# 2. 参与角色

# 3. 前置条件

# 4. 主流程

| 步骤 | 操作者 | 动作 | 系统响应 | 状态变化 | 可观察结果 |
|---|---|---|---|---|---|

# 5. 分支流程

# 6. 异常流程

# 7. 回退、取消与重试

# 8. 涉及的业务规则

# 9. 涉及的接口与数据

# 10. 未决问题
```

### 7.5 状态机模板

文件：`workflows/<module_id>/STATE-<id>.md`

```markdown
---
id: STATE-<MODULE>-001
title: <对象>状态定义
knowledge_type: WORKFLOW
project_id: <project_id>
module_id: <module_id>
source_type: DESIGN_DOC
source_ref: <来源及定位>
source_version: <来源版本>
product_version: ["<适用版本>"]
platforms: ["all"]
evidence_level: E2
status: draft
owner: <owner>
reviewer: null
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
effective_from: null
effective_until: null
tags: []
related_ids: []
---

# 1. 状态列表

| 状态 ID | 状态名称 | 含义 | 终态 | 说明 |
|---|---|---|---|---|

# 2. 状态转换

| 当前状态 | 触发事件 | 前置条件 | 目标状态 | 不允许的条件 |
|---|---|---|---|---|

# 3. 状态不变量

# 4. 并发与重复操作约束

# 5. 状态查询与验证方式

# 6. 来源与未决问题
```

### 7.6 接口文档模板

文件：`interfaces/<module_id>/API-<id>.md`

```markdown
---
id: API-<MODULE>-001
title: <接口名称>
knowledge_type: INTERFACE
project_id: <project_id>
module_id: <module_id>
source_type: API_SPEC
source_ref: <OpenAPI operationId、文件或链接>
source_version: <接口版本>
product_version: ["<适用版本>"]
platforms: ["all"]
evidence_level: E2
status: draft
owner: <owner>
reviewer: null
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
effective_from: null
effective_until: null
tags: []
related_ids: []
---

# 1. 接口用途

# 2. 请求方式与路径

# 3. 身份认证与权限

# 4. 请求参数

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|

# 5. 响应字段

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|

# 6. 错误码与异常

# 7. 幂等、重试与并发约束

# 8. 测试数据准备

# 9. 结果查询与验证

# 10. 来源与未决问题
```

<a id="testing-standard-template"></a>

### 7.7 测试规范模板

文件：`testing/project_test_standards.md`

```markdown
---
id: TEST-SPEC-PROJECT-001
title: 项目测试规范
knowledge_type: TEST_SPEC
project_id: <project_id>
module_id: null
source_type: TEST_STANDARD
source_ref: <来源>
source_version: <版本>
product_version: ["all"]
platforms: ["all"]
evidence_level: E3
status: draft
owner: <owner>
reviewer: null
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
effective_from: null
effective_until: null
tags: []
---

# 1. 测试范围与原则

# 2. 测试用例结构要求

# 3. 前置条件规范

# 4. 测试步骤规范

# 5. 预期结果规范

# 6. 测试数据规范

# 7. 边界与异常覆盖要求

# 8. 证据与结果记录要求

# 9. 项目特殊约定
```

### 7.8 自动化能力模板

文件：`automation/limitations.md`

```markdown
---
id: AUTO-LIMITATIONS-001
title: 自动化能力与限制
knowledge_type: AUTOMATION
project_id: <project_id>
module_id: null
source_type: AUTOMATION_DOC
source_ref: <来源>
source_version: <版本>
product_version: ["<适用版本>"]
platforms: ["all"]
evidence_level: E3
status: draft
owner: <owner>
reviewer: null
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
effective_from: null
effective_until: null
tags: []
---

# 1. 自动化框架与版本

# 2. 支持的客户端和协议

# 3. 元素定位能力

# 4. 数据准备能力

# 5. 状态读取与断言能力

# 6. 异步、并发与等待能力

# 7. 不支持或不稳定的场景

# 8. 环境与权限限制

# 9. 相关示例
```

### 7.9 历史缺陷模板

文件：`historical_bugs/<module_id>/BUG-<id>.md`

```markdown
---
id: BUG-<MODULE>-001
title: <缺陷标题>
knowledge_type: HISTORICAL_BUG
project_id: <project_id>
module_id: <module_id>
source_type: BUG_TRACKER
source_ref: <缺陷系统链接或编号>
source_version: <发生版本>
product_version: ["<发生版本>"]
platforms: ["<平台>"]
evidence_level: E4
status: draft
owner: <owner>
reviewer: null
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
effective_from: null
effective_until: null
tags: []
related_ids: []
---

# 1. 缺陷现象

# 2. 发生条件

# 3. 影响范围

# 4. 根因

# 5. 修复版本与修复说明

# 6. 回归验证

# 7. 当前是否仍适用

# 8. 是否沉淀为正式规则

# 9. 审核结论
```

历史缺陷不得因“曾经发生”而自动成为当前规则。若要沉淀为正式规则，应另建 `RULE-*` 文档，经过业务负责人审核，并保留与原缺陷的关联。

## 8. 来源、引用与证据定位

### 8.1 来源必须可追溯

每份知识文档必须能够回答：

- 原始资料是什么？
- 原始资料由谁维护？
- 对应哪个版本？
- 当前知识由谁整理？
- 谁审核了整理结果？
- 内容适用于哪个产品版本、平台和模块？
- 如何定位回原始资料的具体章节或字段？

### 8.2 `source_ref` 规范

优先级建议：

1. 仓库内相对路径 + 标题或锚点。
2. 需求/缺陷/接口系统的稳定 ID。
3. 官方文档 URL + 章节定位。
4. 会议决策编号 + 会议日期 + 结论条目。

不允许只填写“产品文档”“会议纪要”“开发说的”等无法定位的描述。

### 8.3 检索片段必须保留定位信息

每个可检索 chunk 至少应能回溯：

- `project_id`
- `knowledge_id`
- `knowledge_type`
- `module_id`
- `source_ref`
- `source_version`
- `evidence_level`
- `status`
- `product_version`
- `platforms`
- `heading_path`
- `chunk_id`
- `content_hash`
- `git_commit`

检索结果必须返回来源定位信息，不得只返回一段脱离上下文的文本。

## 9. 知识冲突与缺口管理

### 9.1 冲突处理

当多份知识互相矛盾时：

1. 不得简单按检索分数最高者决定。
2. 先比较来源权威性、审核状态、产品版本和生效时间。
3. 仍无法消除冲突时，登记冲突并暂停将相关知识用于强制判定。
4. 对影响评审结论的冲突，应输出人工确认需求。
5. 解决冲突后保留旧记录及替代关系，不得无痕覆盖。

冲突记录建议字段：

```yaml
id: CONFLICT-001
project_id: <project_id>
related_knowledge_ids:
  - RULE-001
  - REQ-002
description: <冲突描述>
impact: <影响的评审范围>
decision_status: pending
documentation_status: pending
implementation_status: pending
verification_status: not_verified
owner: <责任人>
resolution: null
decided_at: null
```

### 9.2 知识缺口处理

缺失资料不等于业务规则不存在。应将缺口显式记录。

```yaml
id: GAP-001
project_id: <project_id>
module_id: <module_id>
topic: <缺失主题>
missing_knowledge_type: BUSINESS_RULE
description: <当前缺少什么资料>
affected_review_dimensions:
  - business_correctness
  - expected_result
risk: high
owner: <责任人>
status: open
required_by: <日期或里程碑>
```

评审遇到知识缺口时，应区分：

- `kb_module_missing`：模块尚无可用知识。
- `kb_rule_missing`：缺少判断该问题所需的规则。
- `kb_source_unverified`：来源尚未审核。
- `kb_version_mismatch`：知识版本不适用于当前被测版本。
- `kb_conflict`：存在未解决的知识冲突。
- `kb_retrieval_insufficient`：资料存在但未检索到充分证据。

这些是建议的缺口原因标识，最终枚举应与 TestJury 现有 API、审计和评审结果 Schema 统一后再落地。

## 10. 知识审核与发布流程

建议采用以下生命周期：

```text
资料收集
   |
   v
来源登记
   |
   v
结构化整理
   |
   v
格式与元数据校验
   |
   v
业务负责人审核
   |
   +---- 不通过 ----> 退回修改
   |
   v
批准发布
   |
   v
构建检索索引
   |
   v
检索回归测试
   |
   v
知识版本发布
   |
   v
持续监控与定期复审
```

### 10.1 审核职责

| 角色 | 职责 |
|---|---|
| 知识整理者 | 整理来源、编写结构化文档、标记不确定内容 |
| 业务负责人 | 确认业务规则、流程和需求解释是否正确 |
| 测试负责人 | 确认测试规范、验证方式和可观察性描述 |
| 知识库维护者 | 检查元数据、格式、引用、版本和索引构建 |
| 发布负责人 | 批准知识版本进入正式评审范围 |

一个人可以承担多个角色，但审核记录必须明确实际责任人。未经审核的内容不得仅因已合并到 Git 主分支就自动视为正式知识。

### 10.2 发布条件

知识版本发布前必须满足：

- 必需元数据完整。
- 所有正式知识均有可追溯来源。
- `approved` 文档具有审核人和审核日期。
- 没有未处理且会影响本次评审的高风险冲突。
- 失效或被替代知识已从当前检索范围排除。
- 解析和索引构建成功。
- 检索回归集通过。
- 发布记录包含 Git commit、索引构建版本和发布时间。

## 11. 版本与有效性规则

知识有效性至少由以下维度共同决定：

1. 项目是否匹配。
2. 模块是否匹配。
3. 产品版本是否匹配。
4. 平台是否匹配。
5. 生效时间是否匹配。
6. 生命周期状态是否允许使用。
7. 证据等级是否足以支撑当前判断。

不能只使用 `updated_at` 判断知识是否有效。文档最近修改时间不等于业务规则生效时间。

### 11.1 版本变更

- 需求变更应创建新版本或明确记录变更。
- 对业务含义发生变化的规则，优先创建新知识版本，并通过 `supersedes` 关联旧版本。
- 旧版本保留用于历史评审复现，但不得进入新版本评审的默认检索范围。
- 每次评审必须记录使用的知识发布版本。
- 同一评审任务不得在执行中途静默切换知识版本。

### 11.2 失效处理

- 到达 `effective_until` 的知识自动退出当前有效集合。
- 已废弃、已替代、被拒绝和归档知识不得作为当前有效证据。
- 失效知识可以用于历史任务复现，但必须显式标记为历史上下文。

## 12. 检索与数据索引要求

本节定义数据契约，不限定具体算法。

### 12.1 检索前过滤

至少按以下条件过滤：

- `project_id`
- 内容侧 `status = approved`，且平台 `rule_status = published`
- 任务冻结的 `kb_build_version` 必须来自已发布的 active 构建
- 显式选择并冻结的 `review_baseline`
- 当前产品版本
- 当前平台
- 当前模块或明确允许的跨模块知识
- 生效时间
- 知识类型
- 敏感级别和调用者权限

E1–E4 不宜简单作为唯一排序依据；应结合适用性、来源权威性和检索相关性。

### 12.2 Chunk 规则

- 优先按 Markdown 标题层级和语义完整段落切分。
- 不得把一条规则的前置条件与结果拆到互不关联的 chunk。
- 表格应尽量保持行列语义完整。
- 状态转换表、字段约束表等结构化内容应保留表头。
- 每个 chunk 必须保存完整的来源定位和知识元数据。
- 对过长文档可以分层摘要，但摘要不能替代原始证据。
- 评审引用时优先返回原始知识片段，不得只引用自动摘要。

### 12.3 建议索引字段

| 字段 | 用途 |
|---|---|
| `chunk_id` | 检索片段唯一标识 |
| `knowledge_id` | 对应知识文档 ID |
| `project_id` | 项目隔离 |
| `module_id` | 模块过滤 |
| `knowledge_type` | 类型过滤 |
| `content` | 原始片段内容 |
| `embedding` | 向量检索字段 |
| `keywords` | 关键词检索字段 |
| `heading_path` | 章节定位 |
| `source_ref` | 原始来源 |
| `source_version` | 来源版本 |
| `evidence_level` | 证据等级 |
| `status` | 生命周期状态 |
| `product_version` | 适用版本 |
| `platforms` | 适用平台 |
| `effective_from` / `effective_until` | 有效期 |
| `content_hash` | 内容变更检测 |
| `git_commit` | 知识发布追溯 |

以上是逻辑字段建议，不等于要求数据库必须采用同名物理列。具体 Schema 应与现有全局数据字典统一。

## 13. 知识库如何支撑评审

知识库应为评审提供依据，而不是替代 Rubric。

| 评审维度 | 主要知识来源 | 可支持的判断 |
|---|---|---|
| 业务意图与规则正确性 | REQUIREMENT、BUSINESS_RULE | 用例是否违背明确需求或规则 |
| 前置条件充分性 | REQUIREMENT、BUSINESS_RULE、WORKFLOW | 前置状态、权限和数据条件是否完整 |
| 步骤与流程一致性 | WORKFLOW、INTERFACE | 步骤顺序、状态变化和接口调用是否合理 |
| 预期结果可判定性 | REQUIREMENT、BUSINESS_RULE、INTERFACE | 预期结果是否明确且可观察 |
| 测试数据完整性 | BUSINESS_RULE、INTERFACE、TEST_SPEC | 数据准备是否满足规则和约束 |
| 边界与异常覆盖 | BUSINESS_RULE、WORKFLOW、历史缺陷 | 是否遗漏已明确的边界和异常场景 |
| 自动化可行性 | AUTOMATION、INTERFACE、TEST_SPEC | 当前框架和环境是否支持执行与断言 |

### 13.1 评审引用要求

每条依赖知识库的实质性评审意见，应尽可能包含：

- `knowledge_id`
- 来源定位（文件、章节、字段或外部系统 ID）
- 知识版本或 Git commit
- 证据等级
- 适用版本和平台
- 该知识如何支持当前判断

如果没有足够证据，应明确说明“资料不足，无法确认”，而不是将通用经验包装成项目事实。

### 13.2 不得发生的行为

- 不得将待评审用例本身当作其业务正确性的权威依据。
- 不得将历史缺陷直接等同于当前产品规则。
- 不得把 E4 经验作为强制业务 blocker 的唯一依据。
- 不得忽略产品版本和平台差异。
- 不得把检索相似度当成事实可信度。
- 不得因某个规则未被检索到，就断言该规则不存在。
- 不得在没有来源时生成虚假的知识引用。

## 14. 安全与隐私要求

- 知识入库前必须识别个人信息、账号凭据、访问令牌、密钥和其他敏感数据。
- 默认不允许将真实用户数据、生产凭据和不必要的个人信息写入知识库。
- 必须依据项目数据分级和模型准入策略决定哪些内容可以被模型检索。
- 受限资料必须实施访问控制，不能只依赖 Prompt 告知模型不要泄露。
- 日志和检索审计不得记录不必要的敏感原文。
- 外部模型调用前的脱敏要求应沿用 TestJury 现有模型准入与脱敏契约，不在本规范中另行定义一套互相冲突的机制。

## 15. 知识库验收标准

验收分为数据质量、检索质量和评审效果三层。不能只以文档数量或向量入库数量作为通过依据。

### 15.1 数据质量验收

| 指标 | 建议目标 | 验收方式 |
|---|---:|---|
| 正式知识来源可追溯率 | 100% | 抽查全部或全量元数据 |
| 必需元数据完整率 | 100% | 自动 Schema 校验 |
| 正式知识审核记录完整率 | 100% | 检查 reviewer、reviewed_at |
| 当前有效性判断准确率 | 100%（验收样本） | 版本/有效期人工核验 |
| 高风险冲突处置率 | 100% | 冲突台账核验 |
| 失效知识误入当前检索集比例 | 0% | 检索过滤测试 |

### 15.2 检索质量验收

仓库既有知识库方案中的目标可作为首轮参考，最终阈值应由黄金集规模和业务风险确认：

| 指标 | 初始参考目标 |
|---|---:|
| Recall@10 | ≥ 90% |
| nDCG@10 | ≥ 0.75 |
| 证据可定位率 | 100% |
| 跨项目错误召回 | 0 |
| 已失效知识错误召回 | 0 |

必须建立检索黄金集，至少覆盖：

- 精确规则查询。
- 同义改写查询。
- 业务术语查询。
- 跨模块关联查询。
- 版本差异查询。
- 平台差异查询。
- 无答案查询。
- 冲突知识查询。
- 已废弃知识查询。

### 15.3 评审效果验收

至少开展 K0/K1 对照评测：

- K0：不使用项目知识库。
- K1：使用已发布的项目知识库。

对比：

- 业务规则判断准确性。
- 错误问题率。
- 漏报率。
- 无依据结论比例。
- 证据引用正确率。
- 人工复核一致性。
- 评审耗时和 Token 成本。

知识库只有在提高评审质量、降低无依据判断，且没有引入明显错误召回时，才算达到业务价值目标。

## 16. 新项目首批接入清单

建议先选择一个范围清晰的模块，完成以下清单后再开始正式评审。

### 16.1 项目级资料

- [ ] 项目概览与产品定位
- [ ] 当前产品版本
- [ ] 支持平台
- [ ] 模块清单
- [ ] 用户角色与权限
- [ ] 测试环境说明

### 16.2 模块级资料

- [ ] 正式需求或功能规格
- [ ] 核心业务规则
- [ ] 主流程
- [ ] 异常流程
- [ ] 关键状态及状态转换
- [ ] 涉及的接口和数据约束
- [ ] 结果观察与验证方式
- [ ] 未决问题和知识缺口

### 16.3 TestJury 评审准备

- [ ] 明确本次评审适用的 Rubric 版本
- [ ] 明确评审对象与知识库范围
- [ ] 准备真实测试用例作为评审输入
- [ ] 准备人工标注的检索黄金集
- [ ] 准备人工标注的评审黄金集
- [ ] 记录知识库发布版本
- [ ] 完成检索回归
- [ ] 完成 K0/K1 对照评测

## 17. 与现有 TestJury 设计文档的关系

本规范是项目知识数据的补充规范，不应取代仓库已有的治理和契约文档。

落地时应逐项对齐：

| 现有设计主题 | 本规范的关系 |
|---|---|
| 业务定位与范围 | 明确知识库只为约定范围内的用例评审提供依据 |
| 全局数据字典 | 本规范的字段、枚举和 ID 必须与其统一 |
| 知识库维护与发布 | 本规范补充项目资料组织和文档模板 |
| 知识库质量治理 | 本规范补充项目级质量检查和缺口管理 |
| 知识库版本与发布治理 | 本规范补充项目知识的适用版本和引用要求 |
| 知识解析与增量构建 | 本规范提供解析所需的元数据和结构约束 |
| 知识库检索与证据设计 | 本规范补充项目隔离、过滤和来源定位要求 |
| Rubric | 本规范提供事实依据，不修改评审维度和判定规则 |
| 模型准入与脱敏 | 本规范遵循既有数据级别、脱敏和模型调用限制 |

**实施前必须做一次契约对齐审查。** 如果现有文档已经定义了相同字段、枚举、生命周期或指标，应以仓库的单一权威定义为准，避免产生两套相互冲突的规范。

## 18. 建议实施阶段

### 阶段 A：规范冻结

1. 对照全局数据字典核对字段和枚举。
2. 对照知识生命周期文档核对状态机。
3. 对照证据设计核对 E1–E4 定义。
4. 对照发布治理核对审核和发布责任。
5. 明确目录结构和 ID 规则。

交付物：经确认的知识库数据规范及模板。

### 阶段 B：单模块资料整理

1. 选择一个新项目模块。
2. 收集原始需求、规则、流程和接口资料。
3. 建立来源清单。
4. 按模板整理知识。
5. 登记冲突和缺口。
6. 由业务和测试负责人审核。

交付物：一个模块的最小充分知识集。

### 阶段 C：检索试点

1. 对已批准文档进行解析。
2. 构建索引。
3. 建立检索黄金集。
4. 执行检索回归。
5. 检查引用定位和版本过滤。

交付物：可复现的知识库检索试点报告。

### 阶段 D：评审效果验证

1. 选择代表性测试用例。
2. 建立人工评审基准。
3. 执行 K0/K1 对照评测。
4. 分析误召回、漏召回和错误判断。
5. 修订知识组织、检索和引用策略。

交付物：知识库对评审质量的效果评估报告。

### 阶段 E：逐模块扩展

只有在试点达到数据质量、检索质量和评审效果要求后，才扩展到其他模块。

---

## 19. 当前需要项目方确认的决策

以下事项不应由规范作者擅自替项目决定：

| 编号 | 待确认事项 | 建议默认值 |
|---|---|---|
| D-01 | 项目知识目录是否采用 `kb_content/<project_id>/` | 采用 |
| D-02 | 项目与全局知识是否分命名空间 | 分离 |
| D-03 | 独立规则是否必须拥有稳定 ID | 必须 |
| D-04 | 正式知识是否必须经过业务审核 | 必须 |
| D-05 | 是否允许未审核资料参与正式评审 | 不允许 |
| D-06 | 是否允许跨项目召回 | 默认禁止 |
| D-07 | 是否允许 E4 单独支撑业务 blocker | 不允许 |
| D-08 | 评审是否记录知识库 Git commit | 必须 |
| D-09 | 无知识或知识冲突时是否允许模型自行推断 | 允许提出假设，但必须降级并明确标记，不得作为已确认事实 |
| D-10 | 检索指标是否直接采用现有方案目标 | 先作为试点目标，基于黄金集校准 |

## 20. 最终建议

TestJury 的项目知识库应以**可验证的项目事实**为核心，而不是以文档数量为核心。

首批建设应聚焦：

1. 项目和模块边界。
2. 正式需求。
3. 核心业务规则。
4. 业务流程与状态。
5. 接口、数据和结果验证方式。
6. 测试规范及自动化限制。

历史缺陷和专家经验可以逐步积累，不应成为首批接入的阻塞条件。

新项目接入的最低合格标准不是“资料齐全”，而是：

> 对本次纳入评审范围的每个关键判断，TestJury 都能找到适用、有效、已审核且可追溯的依据；找不到依据时，能够明确报告知识缺口，而不是猜测业务事实。

这应当成为 TestJury 项目知识库建设和验收的核心原则。
