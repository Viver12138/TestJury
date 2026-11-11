# 评审团 Agent · 设计文档

> **输入**：一份功能测试用例
> **输出**：一份评审报告（结构化 JSON + 人读 Markdown）
> **核心**：v1 严格限定**功能测试用例**质量评审；1 名主审 `qwen-max` + 2 名陪审 `deepseek-flash` / `kimi-k3` 独立盲评与投票；正式生产默认拓扑待 A–E 对照实验确定，主审仲裁按条件触发；AI 只出评审意见，不代替最终审批
> **形态**：FastAPI 异步 HTTP 服务，PostgreSQL + pgvector
> **状态**：**design-v1.13 + M0 实现 + M1 真实模型接入**（Qwen3.8-Max / DeepSeek-Flash / Kimi-K3.1-Pro 已跑通真实评审；274 条测试通过；知识库与生产部署未开始）· 2026-11-11

---

## 1. 一句话定位

一个**异步 HTTP 服务**：测试流水线把功能测试用例 POST 进来，服务调度三个模型独立盲评，系统融合候选问题并组织投票，由主审终审，产出一份**带证据引用、可追溯、可人工复核**的评审报告。

评审的对象是**用例质量**（覆盖是否完整、步骤是否可执行、预期是否可判定、能否自动化），不是功能本身是否正确。

### 1.1 版本体系（避免设计版本与产品版本混用）

| 版本维度 | 当前值 | 用途 |
|---|---|---|
| 设计基线版本 | `design-v1.13` | 本仓库设计文档整体迭代版本；各文档文首 `vX.Y` 即此版本 |
| 产品版本 | `product-v1.0`（规划） | 实际交付给用户的产品范围；见 `docs/00` §10 |
| Rubric 版本 | `rubric-0.2.0` | 评审标准；`rubric/rubric.yaml` |
| 报告格式版本 | `report-1.0` | `schemas/report.schema.json` |
| 知识库数据版本 | `kb-<content_hash>` | 每次发布的内容快照 |

- 设计基线版本**不代表**产品功能已交付；产品版本按 `docs/00` 的 v1/v1.5/v2 路线单独管理。
- 报告、Rubric、知识库各自版本化，互不替代（见 `docs/01` §10、`docs/22`）。
- 发布沟通必须写明维度，例如"design-v1.6 冻结、product-v1.0 未发布"。

## 2. 共识决策记录

| # | 决策项 | 结论 |
|---|---|---|
| 1 | 输入形态 | 结构化 JSON 为主（步骤数组），`raw_text` 纯文本兜底 |
| 2 | 评审团构成 | 1 主审 + 2 陪审，三个**不同厂商/家族**的模型 |
| 3 | 模型分工 | 主审 `qwen-max`；陪审甲 `deepseek-flash`（业务/需求视角）；陪审乙 `kimi-k3`（测试设计 + 自动化可行性视角）；`kimi-k3` 为内部别名，真实 Model ID 以接口验证为准 |
| 4 | 主审职责 | 盲评一次 + 投票一次；**仲裁按条件触发**（存在分歧/证据冲突/补充意图时才调用），三次调用不是固定次数 |
| 5 | 三方关系 | 三份盲评意见**等权**，主审在自己那份上只有一票 |
| 6 | 主审权限 | 可否决陪审，但必须写明驳回理由；驳回的阻断项进入人工复核清单 |
| 7 | 知识库 | 混合检索：结构化过滤（模块→功能点→规则/术语/已知限制/历史缺陷）+ 关键词（trigram/精确）+ pgvector 向量 + RRF + Reranker；原文切片按知识类型 |
| 8 | 知识库范围 | 从零建，先做 3–5 个高频模块，跑通后再扩 |
| 9 | 知识库缺口 | 评审中反复出现的"无依据判断"自动聚合为缺口清单，定期人工确认后入库 |
| 10 | 知识库未覆盖 | 降级评审 + 报告顶部醒目提示；问题区分"基于知识库验证"与"基于通用准则推断" |
| 11 | 问题融合 | 规则键分桶（步骤号 ±1 容差）→ embedding 召回疑似重复 → Reranker 判同一根因 → 高确定性合并，边界交仲裁 |
| 12 | 结论档位 | AI 结论 `blocked` / `conditional` / `need_human`；人工状态 `pending` / `approved` / `rejected` / `changes_requested`；**系统永不自动判"通过"** |
| 13 | 报告形态 | JSON（主数据）+ Markdown（人读），附录附三份原始意见、投票明细与证据清单 |
| 14 | 服务形态 | 异步作业：创建任务 → 轮询/webhook 取结果；另提供批量接口 |
| 15 | 技术栈 | Python + FastAPI + PostgreSQL + pgvector + PostgreSQL 持久化任务队列 |
| 16 | 并发 | 单机并发 4 个评审任务，超出排队 |
| 17 | 鉴权 | 内部服务，API Key + 调用方标识 |
| 18 | 存档 | 每次模型调用的完整 prompt/输出、token 数、耗时全部落库 |
| 19 | 版本追溯 | 报告记录知识库版本 + rubric + prompt + 检索配置 + embedding profile + 模型配置版本 + 报告 Schema 版本 |
| 20 | 合规 | 三个厂商 API 允许调用；按公司要求记录调用日志 |
| 21 | 验收 | 30 份人工标注种子集 + 检索黄金集 + 融合正负样本冷启动；分 dev/验证/冻结/回归四套；上线后靠人工复核结论回写持续积累真值 |
| 22 | 规模 | 单批 ≤ 50 份，日 ≤ 200 份 |
| 23 | v1 范围 | 评审链路 + 报告 + 复核回写 + 知识库缺口清单 + 批量接口 |
| 24 | v1 不做 | 自动改写用例、复评 diff、知识库编辑界面、看板、多团队隔离 |
| 25 | 检索链路 | 多查询构建 → 结构化过滤 → 关键词（trigram/精确）→ 向量 → RRF → Reranker 精排 → 证据包（非单次向量检索） |
| 26 | 证据溯源 | 每条证据带 `source_ref` / `heading_path` / 检索通道 / rerank 分数，结论可回查原文 |
| 27 | Embedding 管理 | 独立 `embedding_profiles`；换模型 = 新 profile + 新索引，评测后切换 |
| 28 | 问题融合 | 规则键分桶 → 向量召回 → Reranker 判同一根因 → 高确定性才合并 |
| 29 | 投票机制 | 独立投票轮：`accept` / `reject` / `not_assessed` / `uncertain`；未提及 ≠ 反对 |
| 30 | 评审上下文 | 增加 `test_scope`（功能点覆盖）与 `automation_context`（框架能力），缺失时限制结论强度 |
| 31 | 任务队列 | PostgreSQL 持久化队列 + 租约 + 重试；不再用进程内 `asyncio.Queue` |
| 32 | 验收体系 | 检索黄金集 + 评审黄金集；检索/重排/评审/融合/仲裁/报告分层指标 |
| 33 | 置信度 | 不做"1/2/3 方 = 0.6/0.85/0.95"硬映射；未校准为 `null`，校准后写入 |
| 34 | v1 范围 | 只做**单条用例质量评审**；功能点覆盖评审 v1.5 另立，`test_scope` 只做"未覆盖已列场景"提示 |
| 35 | AI/人工分离 | `ai_verdict` 不可变；人工决定走 append-only 的 `review_decisions`，派生 `human_status` |
| 36 | 失败处理 | 按阶段分级降级：核心评审失败即失败，Embedding/Rerank 可降级，投票缺失记 `not_assessed`，新增 `completed_with_warnings` |
| 37 | 证据类型 | 增加 `evidence_type` / `evidence_strength`；历史缺陷只能提示"曾出现"，不能证明当前仍存在 |
| 38 | Embedding 维度 | v1 固定 1024 维并加约束；多维度需分表/分列，不在 v1 |
| 39 | 中文关键词检索 | v1 = `pg_trgm` 三元组 + RULE-ID/字段/数值精确匹配；`zhparser` 可选升级 |
| 40 | 幂等与重跑 | `idempotency_key` 覆盖输入与全部版本；`generation` 代次 + `superseded_by`（仅 `review_jobs` 代次链）；同一 key 并发串行化，不返回 409 `DUPLICATE`（`docs/03` §1.1） |
| 41 | 模型配置 | `config/models.yaml` 注册表 + Chat/Embedding/Rerank 三类适配器 |
| 42 | 知识库事实源 | Git + Markdown 为唯一事实源，PostgreSQL 只是索引；`kb_versions` 发布/回滚 |
| 43 | 报告结构 | `report_json` 为唯一事实源，`report_schema_version` 版本化；Markdown 只做渲染 |
| 44 | 投票隔离 | 投票材料隐藏 `proposed_by` 与他人原始论证；统一中性描述；记录初审/投票翻转用于锚定分析 |
| 45 | 主审约束 | 原始记录不可改；仲裁前后状态留痕；人工复核触发由服务端计算，模型不能取消 |
| 46 | 成立性与严重级 | `validity` 与 `severity` 两个独立字段；严重级跨两级分歧转人工；blocker 需同时满足成立、严重级、无多数否决 |
| 47 | 模型失败阈值 | 3/3 完整；2/3 降级并标 `review_completeness`；1/3 不出正式 AI 结论；0/3 失败；主审不可由陪审替代 |
| 48 | 报告投影 | `issues` 为 `report_json` 的只读派生投影，同事务写入，可重建、可校验 |
| 49 | 幂等响应 | 命中返回 200 + 原任务真实状态 + `idempotent_replay` + `generation` + `report_available`，不再统一 `done`，也不返回 409 |
| 50 | 性能口径 | 排队/模型调用/评审执行/端到端/批量分开统计 P50/P95/P99，压测后定门槛 |
| 51 | 证据分级 | E1 权威规则 / E2 需求与功能 / E3 测试规范 / E4 推断；无 E1/E2 不得判 blocker；同级冲突转人工 |
| 52 | 输入质量 | 增加输入检查：硬错误 422，软问题记 `input_quality`，与模型发现的问题分开展示 |
| 53 | Prompt/模型注册 | `config/prompts.yaml` + `prompt_registry`；区分内部别名、供应商产品名与真实 Model ID |
| 54 | 权限来源 | 角色由服务端按 API Key 查授权表；客户端 `X-Role` 不作为授权依据；`admin` 与 `approver` 分离 |
| 55 | 候选问题 | 新增 `review_candidates` 承接融合产物；投票挂 `candidate_id`；`issues` 只做最终投影 |
| 56 | 审批记录 | `review_decisions` 只 INSERT，按 `decision_no` 取当前有效决定，不用 `superseded_by` 指针 |
| 57 | 权重语义 | Rubric 维度权重只影响提示重点；投票三方等权、一方一票；严重级只统计 accept 票 |
| 58 | 审批边界 | 审批人 ≠ 提交人（可配置）；2/3 与 1/3 降级分级；新 generation 用 `parent_review_id` 关联，不继承旧状态 |
| 59 | 模型验收 | 角色可先冻结，真实 Model ID / 版本 / 并发必须实测后标 `verified` |
| 60 | 证据优先级 | 判定顺序：状态/时效 → 适用性 → E1–E4 → 冲突转人工；失效规则不进入检索 |
| 61 | 规则事实源 | `rubric.yaml` 是机器可执行事实源；Markdown 仅说明；Prompt 只引用；`verdict.py` 唯一计算入口 |
| 62 | 校验分层 | API 同步硬校验（400/422，不建任务）；Worker 只做软校验并记 `input_quality`，不再返回 422 |
| 63 | 候选向量 | 新增 `candidate_embeddings`，融合/投票前写入；`issue_embeddings` 只服务最终问题 |
| 64 | 投票防锚定 | 隐藏 `severity_proposal`、他人投票与论证；标准化描述不得带严重级倾向 |
| 65 | 证据归属 | 证据按 claim 绑定，`evidence_status` 五态；融合不得提高证据强度 |
| 66 | 决策真值表 | `docs/12` 定义全部组合；`verdict.py` 唯一入口，API/Worker/渲染不得各写一套 |
| 67 | 任务恢复 | 单次/阶段/任务/租约四层超时；20 分钟总超时；阶段 Checkpoint 从失败处恢复 |
| 68 | 用例版本 | `case_version`（内容）与 `generation`（评审代次）分开 |
| 69 | 批量状态 | 统一 `partially_completed`，成功保留、失败可单独重跑 |
| 70 | 知识库治理 | 规则生命周期 + 创建/审核/发布职责分离；质量指标与差异报告 |
| 71 | 供应商隐私 | 逐家记录数据保留、训练使用、存储区域、日志与企业协议 |
| 72 | 报告不可变 | `report_locked_at` 后禁止更新；更正只能新建 generation |
| 73 | 全局数据字典 | 以 `docs/17` 为唯一字典；代码枚举、DB CHECK、API Schema、Prompt 枚举同源 |
| 74 | Claim 证据聚合 | 核心 claim 必须 supported 才可判 blocker；非核心缺失标 partially 并转人工 |
| 75 | 仲裁边界 | 主审只出结构化意见；服务端按真值表计算；条件仲裁并记录 `arbitration_required` |
| 76 | 故障矩阵 | 角色 × 阶段 × 错误类型 × 重试 → 最终状态；不按模型数量一概而论 |
| 77 | 恢复版本冻结 | 创建时冻结全部版本；恢复不切换；`input_digest` 覆盖阶段依赖 |
| 78 | Profile 兼容 | 增加 reranker profile 与文本模板版本；不同 profile 向量不比较 |
| 79 | 阶段执行历史 | `review_stages` 当前态 + `review_stage_attempts` 历史，不覆盖重试记录 |
| 80 | 投票完整性 | 每条候选独立 `vote_completeness`；<2 票该候选转人工 |
| 81 | 输出质量门禁 | 统一错误分类与重试/丢弃/阻断规则（`docs/18`） |
| 82 | API 错误码 | 统一 envelope、`retryable`、异步失败表达（`docs/19`） |
| 83 | 容量设计 | 队列/供应商限流/预算/隔离/压测，Worker=4 不是容量结论（`docs/20`） |
| 84 | 端到端验收 | 质量/可靠性/性能/成本/安全门槛与发布门禁（`docs/21`） |
| 85 | 反馈治理 | 反馈先进待审核池，复核后入冻结集，不直接改规则（`docs/23`） |
| 86 | 备用模型 | 备用策略必须在创建任务时冻结；不允许恢复时临时换模型；实际模型写入报告与审计 |
| 87 | 预算不足 | 不得静默跳过投票；投不到票的候选标 `need_human`，报告标 `completed_with_warnings`，不出正式完整结论 |
| 88 | 核心 Claim | 由 Rubric 约束、模型提出、服务端验证；`claim_role=core/supporting`，模型不能随意提升核心性 |
| 89 | 部分证据 blocker | `partially_grounded` 的 blocker 仍可 `blocked`，但必须进人工复核清单，并在报告中标注"证据部分支持" |
| 90 | 三模型架构 | 角色可先冻结；是否保留完整三模型由 A–E 对照实验决定，实验前不宣称其必要性 |
| 91 | 审批身份 | 提交可用系统级 API Key；审批必须个人可信身份，禁止多人共用 Key 审批 |
| 92 | 指标口径 | 统一 Recall/Precision/FDR/FNR 定义；07 与 21 的门槛必须一致，禁止同名不同义 |
| 93 | Decision Trace | v1 报告增加问题判断链（发现 → 融合 → 投票 → 证据 → 仲裁 → verdict） |
| 94 | 知识库权限 | 发布/回滚仅 `kb_publisher`；`admin` 不自动拥有；10/11/16/17 统一 |
| 95 | 预算降级 | Reranker 可跳过；投票不可静默跳过；盲审不足最低数不出正式结论 |
| 96 | API 错误结构 | 以 `docs/19` 为唯一规范；`INVALID_CASE`（400）与 `INPUT_INVALID`（422）分层 |
| 97 | 幂等语义 | `case_version` 业务版本、`input_hash` 内容指纹、`generation` 重跑代次、`idempotency_key` 复用标识；内容变则 hash 变 |
| 98 | 指标命名 | 用 FDR（FP/(TP+FP)）替代误用 FPR；High-risk Recall 分母为人工 blocker+major |
| 99 | Rubric 落地 | 仓库新增 `rubric/rubric.yaml`、`schema.json`、`README.md`、`versions/`；CI 校验 |
| 100 | 生产拓扑 | 实现支持 single/dual/multi；默认拓扑由 A–E 实验决定，不写死三模型 |
| 101 | 模型准入 | 注册表记录上下文/JSON/并发/RPM/TPM/延迟/成本/数据政策；状态 `unverified/testing/verified/deprecated` |
| 102 | 超时矩阵 | 补 KB/融合/verdict/DB 阶段预算；完整阶段 805s，任务总超时 20 分钟 |
| 103 | 知识库准入 | 单模块试点 + 最低规则数 + RULE-ID/来源/范围/审核/检索回归/冲突裁决 |
| 104 | 复核队列 | v1 先实现队列、优先级、处理人、状态、耗时与结论；复杂 SLA 后置 |
| 105 | case_id 作用域 | v1 全局唯一；多团队时引入 `project_id/tenant_id` 组合，不提前做 |
| 106 | 历史重评 | Rubric/KB 更新不自动重评；需新建 generation 并记录触发原因 |
| 107 | 2/3 结论 | 2/3 可出正式结论但标不完整；候选需 2 票一致；blocker 必进人工；1/3 无结论；以 `docs/12` 为准 |
| 108 | 租约栅栏 | 增加 `fencing_token`；阶段/终稿写入必须带令牌校验，旧 Worker 写入被拒 |
| 109 | 批量幂等 | 批次级 + 子任务级幂等；`force` 默认只重跑失败子任务，`force_all` 整批重跑 |
| 110 | 报告删除 | 区分修正（新 generation）、归档（限访问）、合规删除（删除/匿名化 + 审计） |
| 111 | 知识解析门禁 | 元数据/切片/正文/回溯/Embedding/检索任一失败即阻断发布 |
| 112 | 增量构建 | 内容哈希增量；删除规则在新版本显式体现；旧版本按任务引用保留 |
| 113 | 知识问题分型 | `knowledge_missing` / `retrieval_missed` / `knowledge_conflict` / `knowledge_outdated` |
| 114 | 三模型实验 | 增加等预算/等成本对照、错误重合、Incremental Valid Issue Rate |
| 115 | 融合硬约束 | Claim/Evidence/RootCause 三者一致才允许自动合并 |
| 116 | Claim 冻结 | 投票后 claim 结构冻结；仲裁只能补证据/解释，不能改 core 或改投票对象 |
| 117 | 字段信任边界 | 模型不得输出 `ai_verdict`/状态/权限；服务端计算；出现即丢弃 |
| 118 | 契约与测试 | `schemas/report.schema.json` 落地；Mock 测试环境与迁移/部署协议见 24–27 |
| 119 | 报告 Schema 兼容 | 历史报告不自动迁移；按版本读取；渲染器多版本；转换只生成派生数据 |
| 120 | 预算模型 | 任务/阶段/模型/重试/仲裁/批次分层；核心阶段预留；软/硬预算与已启动调用策略 |
| 121 | 附件能力 | v1 支持附件引用、SHA-256、不可变与删除；不做 OCR；附件变化影响 `input_hash` |
| 122 | 数据保留 | 原始数据分级授权；删除覆盖 DB/对象存储/备份/供应商；审计留最小字段 |
| 123 | 实验统计 | 样本量、配对比较、95% CI、分层、模型更新后重跑；不只看点估计 |
| 124 | fencing 修正 | 仅所有权转移时递增；正常续租不变；续租失败立即停止写入 |
| 125 | 字段命名 | 统一 `human_review_items`；删除 `human_review_list` |
| 126 | 指标口径 | Strict Blocker Recall / High-risk Recall / Blocker Detection Recall；FDR 与 FPR 不混用 |
| 127 | Rubric 校验 | Schema 加强 required/enum/const/range；业务约束由 Python 校验器覆盖 |
| 128 | 复核层级 | Issue 级与 Report 级分离；支持转派/重开/多 generation |
| 129 | 缺口去重 | `module+function_point+suspected_rule+root_cause` 组合键；相似转人工合并 |
| 130 | 模型复验 | 记录 last_verified_at/测试集版本；供应商版本/能力变化触发复验 |
| 131 | 取消协议 | `cancel_requested_at`；阶段边界检查；取消不出终稿（v1.5） |
| 132 | 原始数据权限 | `model_runs.raw_*` 仅 admin/审计；脱敏、导出审计、独立保留期 |
| 133 | 超时算法 | 795s 阶段 + 10s DB = 805s；20 分钟总超时含重试不含排队 |
| 134 | 部署目标 | 全局并发 = 副本×每进程；RPO ≤15min、RTO ≤2h（初始） |
| 135 | 附件能力 | v1 接受附件引用 + SHA-256 + 不可变 + 删除；**不做 OCR/图片理解**；附件变化影响 `input_hash` |
| 136 | 人工复核队列 | v1 实现最小复核队列 API（队列/优先级/处理人/状态/耗时/结论），不做管理后台 |
| 137 | 模型拓扑 | 实现 single/dual/multi；默认拓扑由 A–E 实验决定，不写死三模型 |
| 138 | 数据保留 | 原始 Prompt/响应分级授权保存；支持合规删除（DB/对象存储/备份/供应商），审计留最小字段 |
| 139 | 部署范围 | v1 单机 Docker Compose；API 与 Worker 分进程、多 Worker 副本；暂不做 Kubernetes/多机 |
| 140 | 附件闭环 | 服务端上传接口；本机持久化卷；白名单 MIME/大小；SHA-256 校验；**v1 不发送给模型**；随评审删除 |
| 141 | 复核任务实体 | 独立 `human_review_tasks`（issue/report、优先级、处理人、状态、期限、历史）；与报告 items 分离 |
| 142 | 拓扑正式语义 | `single` 仅实验不出正式结论；生产至少 `dual`；`multi` 按 3 人规则；缺席不计票 |
| 143 | Rubric 发布 | 使用 SemVer；当前 `0.2.0 draft`；上线前必须 `published`；任务冻结版本 |
| 144 | Prompt 动态参与者 | 仲裁输入改为 `topology + participants[] + absent[]`，不再固定三份 |
| 145 | Schema 严格化 | 报告 `summary/votes/human_review_items/decision_summary/kb_gaps` 明确结构；Rubric 业务校验器 |
| 146 | 全局决策登记 | `docs/08` §2.0 PD-001–005 `approved`；事实源表唯一 |
| 147 | 数据生命周期 | 存储位置/权限/保留/删除/验证五列；备份、对象存储、供应商侧一并处理 |
| 148 | 上下文超限 | 证据按等级/相关性裁剪；核心证据无法保留则转人工；记录裁剪原因与完整性影响 |
| 149 | 模型准入报告 | 每模型一份报告：真实 ID/JSON/上下文/输出/限流/延迟/成本/数据政策/稳定性 |
| 150 | 反馈评测追溯 | review→issue→feedback→sample→dataset 版本链；调参集与验收集隔离 |
| 151 | 契约 CI | 枚举/状态机/Schema/API/DB/Prompt/Rubric/文档路径自动检查 |
| 152 | RPO/RTO 演练 | 目标值须通过季度恢复演练验证，不只在文档声明 |
| 153 | 数据契约唯一 | `docs/17` 为全局字典；Pydantic/DB/JSON Schema/API/Prompt 必须由 CI 对齐 |
| 154 | 幂等响应 | 幂等命中统一 200 + `idempotent_replay=true`；`force` 新建代次 202；旧代次运行中 `force` 返回 409 `REVIEW_IN_PROGRESS`；删除 409 `DUPLICATE`；同键不同体 422 |
| 155 | 复核生命周期 | 任务状态 + 结果 + append-only 事件；支持重开/转派/多人复核/多 generation |
| 156 | 角色/参与者/模型 | `role_id` ≠ `participant_id` ≠ 模型实例；创建时快照，故障切换记 actual_model |
| 157 | 五层校验 | 格式→引用→证据→适用性→决策；模型置信度不参与可信度 |
| 158 | 附件删除 | 历史报告保留引用元数据但不可下载；物理文件异步清理，DB 记录标记 |
| 159 | 统计单位 | Case/Issue/Claim/Run 分开声明，禁止混算 |
| 160 | 增量价值 | Incremental Valid Issue Gain、Cost per Valid Issue、Human Override Rate |
| 161 | 缺口处理 | `gap_type` + `gap_resolution` 记录实际动作，关闭不等于补规则 |
| 162 | 决策索引 | `design/decisions.yaml` 机器可读；docs/08 §2.0 为权威 |
| 163 | 健康检查 | `/livez`、`/readyz`、`/healthz` 兼容、`/metrics` |
| 164 | 附件卷 | 所有 API/Worker 共享同一附件卷；多机前必须换对象存储 |
| 165 | Schema 同步 | 报告 Schema 补 `cancelled`、issue 证据/置信度/校验状态、participants |
| 166 | 复核状态 | 统一 `pending/in_progress/completed/cancelled`；不再用 `done` |

> **v1.13 设计变更（2026-11-10，已批准）**：D222 授权表与附件"内容寻址 + 评审绑定"、D223 `issues` 投影同事务且可重建、D224 模型 Adapter 协议与注册表。变更记录见 [design/changes/2026-11-10-m1-implementation-gaps.md](design/changes/2026-11-10-m1-implementation-gaps.md)。
| 167 | 复核结果 | Issue 5 种、Report 3 种（含 `reject`）；DB CHECK + API 层级校验 |
| 168 | 幂等历史 | README #49 / D28 的旧幂等字段名全部改为 `idempotent_replay` |
| 169 | 健康检查 | `/livez` 存活；`/readyz` 就绪；`/healthz` 等同 readyz；依赖失败 503 |
| 170 | 附件删除 | 先软删禁止下载，异步清物理文件，保留最小元数据；不级联物理删除 |
| 171 | 多人复核 | 一致采纳；冲突升级裁决；`version` 乐观锁；事件不覆盖 |
| 172 | Issue/Report 关系 | 两个独立状态机；blocker 未完成不得 approve；新 generation 使旧审批失效 |
| 173 | 阶段完成 | `stages_completed` 只含 succeeded；`stages_skipped` 单列 |
| 174 | 决策状态 | `status/validation_status/implementation_status/release_status` 四维 |
| 175 | M0 准入 | 10 项可验证退出条件；M0 不接真实模型 |
| 176 | 幂等唯一口径 | `docs/03` §1.1 为唯一来源（S1–S7）；未 force 200、force 202、运行中 force 409 `REVIEW_IN_PROGRESS`；无 409 `DUPLICATE` |
| 177 | 契约检查 CI | `scripts/check_contracts.py` 聚合文档/Rubric/报告 Schema/决策索引/Verdict 用例/M0 用例检查；失败输出文件+字段+期望值 |
| 178 | M0 验收用例 | `design/m0_acceptance.yaml`：M0-01–10 每项映射到可执行用例，含前置/输入/步骤/预期/失败判定/自动化/CI Job |
| 179 | Verdict 可执行用例 | `design/verdict_cases.yaml` + `scripts/verdict_reference.py`；固定/参数化/属性/边界用例；`verdict.py` 必须与用例一致 |
| 180 | 决策索引对齐 | `design/decisions.yaml` 的 ID 与 `docs/08` 一一对应，禁止同名不同义；CI 校验唯一性与引用 |
| 181 | 模型 Adapter 契约 | 统一请求/超时/重试/限流/模型标识/Token/成本/异常/JSON 能力/可观测性（`docs/10` §7.4） |
| 182 | A–E 协议冻结 | 12 项协议在实验前冻结并签署；变更即作废重跑（`docs/15` §2.1） |
| 183 | 成本口径分层 | 已发生/已预留/预计/失败/重试/缓存分层；补月预算与超预算行为（`docs/20` §6.3） |
| 184 | 复核运营规则 | 分派/无人认领升级/超时状态/离职与权限变更/人机冲突/并发/抽检/回写（`docs/09` §12.6） |
| 185 | 报告可读性验收 | 任务型验收：完成时间、误解率、复核一致性、主观可用性（`docs/07` §8.7） |
| 186 | 契约清理记录 | 逐处标记 保留/更新/废弃/历史说明，历史语义不得被误读为当前规则（`docs/28` §2） |
| 187 | 决策阶段分层 | `design/decisions.yaml` 增加 `phase`（M0/M1/M4/M5/M6/production）；未到阶段不得自行假设；M0 决策验证通过后才可标 `passed` |
| 188 | 业务基线 | `docs/00` 为业务上位约束；BIZ-001–015 登记于 `docs/08` §2.0.2 与决策索引；CI 校验三处一致 |
| 189 | 测试类型边界 | `case.test_type` **必填**；v1 仅接受 `functional`；缺失 422 `TEST_TYPE_REQUIRED`，其它类型 422 `UNSUPPORTED_TEST_TYPE`；兼容模式仅显式配置+白名单并记录来源 |
| 190 | 业务维度映射 | `docs/04` §2.1 将 `docs/00` §5.2 的 11 个业务维度映射到 Rubric；Rubric 0.2.0 新增 T8/重复冗余 |
| 191 | AI 与审批边界 | `ai_verdict` 永不为 `approved`；最终业务审批由测试负责人或调用方负责；外部门禁由调用方定义 |
| 192 | 业务角色映射 | 测试工程师=`reviewer`、测试负责人=`approver`、调用系统=系统级 Key；`admin` 不自动获得审批权 |
| 193 | 版本体系 | 设计基线 `design-vX.Y`、产品 `product-vX.Y`、Rubric/报告/知识库各自版本化（README §1.1） |
| 194 | Rubric 版本绑定 | 从 `rubric.version` 读版本再定位冻结副本；禁止验收硬编码历史版本（ACC-M0-010） |
| 195 | 完整性语义 | `complete`=适用必需阶段全部成功；`full_participation` 单独表达 3/3；新增 stages_failed/pending |
| 196 | test_type 策略 | 必填；缺失 422 `TEST_TYPE_REQUIRED`；兼容模式仅显式配置+白名单并记录来源 |
| 197 | 身份分层 | `actor_type=service/human`；审批必须个人 OIDC/SSO；Key 可撤销、离职回收、代操作留痕 |
| 198 | 幂等作用范围 | 按接口列出是否幂等、键与重复行为；附件按 SHA-256 内容寻址；审批/反馈不幂等 |
| 199 | 知识库初始化 | 新增 `docs/29`：首批 3–5 模块、来源、准入、粒度、冲突、验收与建设路径 |
| 200 | 供应商数据准入 | 注册表增加 `data_admission_status`/数据等级/脱敏/DPA/审核人；未准入不得生产 |
| 201 | 批量边界 | 批量=多个独立单条评审；不做跨用例覆盖率/依赖推断；单条失败不影响其他条 |
| 202 | Canonical 输入 | Source Adapter → Canonical Test Case → Validation → Pipeline；核心不耦合平台字段 |
| 203 | 验收分层与变更影响 | 七层验收；`design/changes/` 模板与依赖链；变更必须记录影响与回归 |
| 204 | 待决事项登记 | `Q-01`–`Q-18` 与 decisions.yaml 同源；resolved 必须引用决策，open 必须写阶段 |
| 205 | 历史缺陷升级 | 7 项条件 + `origin_type`/`derived_from`/`bug_version`/`fixed_version`/`current_validity_confirmed`；不覆盖历史记录 |
| 206 | A–E 批准规则 | `docs/15` §6.1 唯一来源；硬门槛=召回提升+配对 CI 下界>0、FDR、成本、延迟；阈值签署后冻结 |
| 207 | 知识库帮助度 | 分母=注入知识且进入复核的任务；四类评价；主观帮助度与 K0/K1 客观增量分开 |
| 208 | 报告用户验收 | 三层经验用户 + T1–T6 + 人工评审基线；完成率/误解率/一致率/可执行性门槛 |
| 209 | 成本双层预算 | 技术保护上限 ≤ 业务批准预算；分别审批与变更 |
| 210 | Rubric 发布流程 | 审核→批准→回归→published+冻结副本→可回滚；历史报告保留原版本 |
| 211 | 四状态模型 | designed/implemented/verified/accepted；脚本通过只到 verified |
| 212 | 模型准入看板 | `design/model_admission.yaml`：技术验证 + 数据准入双门槛 |
| 213 | KB 试点台账 | `design/kb_pilot.yaml`：顺序/owner/来源/规则数/用例数/状态 |
| 214 | 复核责任台账 | `design/review_roster.yaml`：主责/备份/抽检/仲裁 |
| 215 | 实验协议台账 | `design/experiment_protocol.yaml`：signed 前必须填全阈值与数据集 |
| 216 | 演练记录台账 | 灾难恢复与合规删除记录字段与验收出口（`docs/27` §6.2） |
| 217 | 阶段映射 | S1–S4 ↔ M0–M6 映射；S2 不要求 Rubric 生产发布；Rubric 分 M0 可加载/M2-M6 效果/production 发布 |
| 218 | 状态转换 | designed→implemented→verified→accepted 及回退/有条件转换；状态历史不覆盖；版本变化证据失效 |
| 219 | 检查分层 | CI 只做结构检查；阶段门禁用 `check_execution_gate.py` 查 owner/证据文件/协议/出口 |
| 220 | A–E 统计设计 | 样本量/α/功效/配对/种子/异常样本/多重比较/提前终止/CI 方法签署前冻结 |
| 221 | KB 业务准入 | 来源/完整性/时效/追溯/版本/冲突/录入-审核-发布责任/失效/类型九维 |
| 222 | 模型复验 | 版本/JSON/上下文/数据政策/延迟/切换触发复验，不自动继承旧验收 |
| 223 | 复核运营 | 主责+备份、角色互斥、利益冲突、最终裁定、积压、反馈闭环 |
| 224 | 报告长期指标 | 采纳率/驳回率/耗时/重复率/证据帮助/修改转化/误解率/争议率 |
| 225 | 错误来源分类 | 输入/知识/检索/模型/融合/服务端/人工七类与处理方向 |
| 226 | 最小质量监控 | 先日志/版本快照/可回放/人工记录，4–6 周后再定告警 |
| 227 | 门禁最低状态 | `stage_gates` 按项要求 owner_assigned/decision_recorded/implemented/verified/accepted，owner 不能代替完成 |
| 228 | 阶段单一事实源 | 删除旧 `stages.exit`；`stage_mapping` 唯一；`baseline` 与 README 设计基线一致 |
| 229 | Rubric 验证拆分 | V-03A 效果验证（M6）与 V-03B 生产发布（production）独立 |
| 230 | 证据 manifest/历史 | `manifest.yaml` 含版本/哈希/有效性；`history.jsonl` 只追加，门禁校验 |
| 231 | 统计字段统一 | 只保留 `statistical_design`；补 MDE/基线比例/聚类 bootstrap/主假设/停止规则 |
| 232 | 正式门禁归档 | 仅 main 正式运行；JSON 结果绑定 sha/branch 并归档为证据 |
| 233 | 阶段/phase 一致 | V-08 改为 M6 生产前业务验收；S1–S3 不得要求 production 项 |
| 234 | 证据哈希强校验 | sha256 必填、64 位 hex、重新计算比对，缺失即失败 |
| 235 | 证据版本锁 | `design/versions.lock.yaml` 对比；code_commit 必填，不适用写 `n/a` |
| 236 | 状态迁移防篡改 | 完整校验 allowed/conditional/证据/批准；history 增加 `prev_hash` 链 |
| 237 | Q-14 拆分 | Q-14 为 M2 协议签署；实验执行与结果归 V-06 |
| 238 | 多证据与验收引用 | `artifacts[]` 支持多份；`acceptance_evidence` 必须能在 manifest 中解析 |
| 239 | Q-14 定位统一 | Q-14=M2 协议签署；V-06 负责实验执行与拓扑决策；CI 校验旧口径 |
| 240 | 按项版本依赖 | 每项声明版本依赖；`code_commit` 与当前 HEAD 严格比较，不用 n/a 绕过 |
| 241 | 复核字段边界 | issue 级 `result`+`reason`；report 级 `review_decisions.decision` |
| 242 | KB 内容/构建版本 | `kb_content_version` + `kb_build_version` 成对记录；重建不覆盖旧构建 |
| 243 | KB 双版本贯通 | DDL/API/幂等键/报告 Schema 全部使用 `kb_build_version`，内容版本单独快照 |
| 244 | 复核/审批单一事实源 | report 级 task 的 `result` 必须为空；审批只写 `review_decisions.decision`；`reason` 统一 |
| 245 | Q-14 文本收口 | docs/08 统一为 M2 协议签署；拓扑决策归 V-06；文本级 CI 检查 |

## 3. 文档索引

| 文档 | 内容 |
|---|---|
| [docs/00-业务定位与范围.md](docs/00-业务定位与范围.md) | **业务上位约束**：产品定位、用户、职责边界、版本范围、BIZ-001–015 |
| [docs/01-架构设计.md](docs/01-架构设计.md) | 流水线、检索链路、融合与投票、AI/人工结论、失败矩阵、队列与幂等 |
| [docs/02-数据模型.md](docs/02-数据模型.md) | PostgreSQL 表结构与 DDL（含 review_decisions、kb_versions、issue_votes） |
| [docs/03-API契约.md](docs/03-API契约.md) | 接口定义、请求/响应 Schema、错误码 |
| [docs/04-评审标准.md](docs/04-评审标准.md) | 共享 rubric、严重级定义、问题分类、结论规则 |
| [docs/05-Prompt草案.md](docs/05-Prompt草案.md) | 预处理 / 主审盲评 / 陪审甲 / 陪审乙 / 投票 / 主审仲裁 六份 Prompt |
| [docs/06-工程结构.md](docs/06-工程结构.md) | 目录结构、配置项、依赖、脚本 |
| [docs/07-验收与回归.md](docs/07-验收与回归.md) | 黄金集建设、质量指标、检索与评审分层指标、回归流程 |
| [docs/08-评审修订与实施计划.md](docs/08-评审修订与实施计划.md) | 两轮评审结论、决策记录、P0 对照、实施路线 |
| [docs/09-人工复核与审批机制.md](docs/09-人工复核与审批机制.md) | AI 结论与人工决定分离、审批状态机、权限、审计、报告展示 |
| [docs/10-安全与可靠性设计.md](docs/10-安全与可靠性设计.md) | 鉴权、密钥、隐私、Webhook、模型可靠性、幂等恢复、成本预算、审计 |
| [docs/11-知识库维护与发布机制.md](docs/11-知识库维护与发布机制.md) | 事实源、切片、Embedding Profile、中文检索、KB 版本、发布与回滚 |
| [docs/12-评审决策真值表.md](docs/12-评审决策真值表.md) | 投票/仲裁/verdict 的唯一判断口径、2/3 与 1/3 处理、禁止组合 |
| [docs/13-任务状态与恢复机制.md](docs/13-任务状态与恢复机制.md) | 状态机、阶段 Checkpoint、四层超时、租约、重试、崩溃恢复 |
| [docs/14-数据一致性与约束.md](docs/14-数据一致性与约束.md) | 外键/唯一约束、候选与最终映射、报告不可变、删除与 Schema 检查 |
| [docs/15-模型组合对照实验.md](docs/15-模型组合对照实验.md) | 单模型/多模型/同模型重复对照、指标、控制条件与结论口径 |
| [docs/16-知识库质量治理.md](docs/16-知识库质量治理.md) | 规则生命周期、职责分离、适用范围、质量指标、差异报告 |
| [docs/17-全局数据字典.md](docs/17-全局数据字典.md) | 所有枚举、字段语义、可空规则、DB/API 映射、权限矩阵 |
| [docs/18-模型输出质量门禁.md](docs/18-模型输出质量门禁.md) | 错误分类、重试、局部丢弃、阻断 Verdict |
| [docs/19-API错误码与契约.md](docs/19-API错误码与契约.md) | 统一错误 envelope、错误码、`retryable`、异步错误表达 |
| [docs/20-并发与资源限制.md](docs/20-并发与资源限制.md) | 队列/Worker/供应商限流/预算/隔离/压测 |
| [docs/21-端到端验收标准.md](docs/21-端到端验收标准.md) | 质量、可靠性、性能、成本、安全门槛与发布门禁 |
| [docs/22-阶段执行历史与恢复协议.md](docs/22-阶段执行历史与恢复协议.md) | Attempt 历史、输入摘要、版本冻结、恢复协议 |
| [docs/23-人工反馈与评测集治理.md](docs/23-人工反馈与评测集治理.md) | 反馈 → 待审核池 → 复核 → 冻结评测集 |
| [docs/24-并发控制与一致性协议.md](docs/24-并发控制与一致性协议.md) | 租约 fencing、重复执行、投票重试、批量幂等、终稿写入 |
| [docs/25-知识解析与增量构建.md](docs/25-知识解析与增量构建.md) | 解析门禁、内容哈希、增量索引、版本隔离、缺口分型 |
| [docs/26-测试环境与端到端测试.md](docs/26-测试环境与端到端测试.md) | Mock 供应商、故障注入、迁移与契约测试 |
| [docs/27-生产部署与运维设计.md](docs/27-生产部署与运维设计.md) | API/Worker 拓扑、迁移、备份、健康检查、扩容 |
| [docs/28-契约清理与自动化验收.md](docs/28-契约清理与自动化验收.md) | 幂等清理记录、契约检查、M0 验收用例、Verdict 可执行真值表 |
| [docs/29-知识库初始化与首批数据建设方案.md](docs/29-知识库初始化与首批数据建设方案.md) | 首批模块选择、来源、准入、粒度、冲突、验收与建设路径 |
| [docs/30-实施推进与验收证据台账.md](docs/30-实施推进与验收证据台账.md) | 四状态模型、open 决策台账、V-01–V-12 验证项、证据模板与执行顺序 |
| [design/execution_plan.yaml](design/execution_plan.yaml) | 执行台账：Q/V 项、owner、阶段、证据（机器可读） |
| [design/model_admission.yaml](design/model_admission.yaml) | 模型技术验证 + 数据准入看板 |
| [design/experiment_protocol.yaml](design/experiment_protocol.yaml) | A–E 实验协议台账（阈值签署前为空） |
| [design/kb_pilot.yaml](design/kb_pilot.yaml) | 知识库首批模块试点台账 |
| [design/review_roster.yaml](design/review_roster.yaml) | 人工复核责任表（主责/备份/抽检/仲裁） |
| [design/changes/TEMPLATE.md](design/changes/TEMPLATE.md) | 设计变更影响分析模板 |
| [scripts/README.md](scripts/README.md) | 契约检查脚本：入口、检查项、输出格式与边界 |
| [design/m0_acceptance.yaml](design/m0_acceptance.yaml) | M0 十项 + P0 四项 + BIZ 业务边界验收用例（40 条，可回填结果） |
| [design/verdict_cases.yaml](design/verdict_cases.yaml) | Verdict 可执行真值表用例（36 条，30 条规则） |
| [rubric/README.md](rubric/README.md) | 机器可执行 Rubric：YAML、Schema、版本副本与 CI 校验规则 |
| [schemas/README.md](schemas/README.md) | 报告 JSON Schema 与版本化规则 |
| [design/decisions.yaml](design/decisions.yaml) | 机器可读决策索引（与 docs/08 对齐） |

## 4. 明确不做（v1）

- **不自动改写用例**：只给修改建议，不产出改写后的用例文本。
- **不做功能点覆盖率评分/报表**：v1 只评审单条用例；覆盖评审 v1.5 另立。
- **不做非功能测试类型正式评审**：性能/安全/兼容/可靠性/可用性等类型在 v1 被 `422 UNSUPPORTED_TEST_TYPE` 拒绝，不用功能 Rubric 强行出结论（`docs/00` §6）。
- **不做自动化脚本生成/执行/环境配置**：只给自动化可行性提示与限制说明。
- **不做自动审批 / 自动放行**：AI 结论是机器评审意见；最终审批由测试负责人或调用方负责。
- **不做第四个模型 / 多 Agent 辩论**：三模型机制未通过评测前不扩复杂度。
- **不做自动 Prompt 调优 / 自动阈值调整**：评测集未冻结前不做。
- **不做复评 diff**：同一用例修改后重新提交视为新评审，不做版本对比（v1.5）。
- **不做知识库编辑界面**：知识库以 Markdown 文件 + Git 管理，发布走脚本（v2）。
- **不做多团队隔离**：单一内部团队使用（v2）。

## 5. 待定事项与风险

| # | 事项 | 说明 / 应对 |
|---|---|---|
| R1 | **知识库素材尚未提供** | 建议最小可用集先覆盖 5 个模块，候选：背包/仓库、挖宝、语音聊天室+打赏、帮会同盟/约战/宣战、奇穴装配（均来自现有测试点） |
| R2 | **黄金集没有现成真值** | 30 份种子集需 1–2 名测试专家标注 2–3 小时；只够流程验证，正式验收前需扩到冻结集；上线后靠复核回写积累 |
| R3 | **模型档次不齐** | `deepseek-flash` 偏轻量，可能拖低业务视角；建议上线前用同一批用例做一次盲测，季度轮换一次视角绑定做校准 |
| R4 | **主审自我偏好** | 主审既盲评、又投票、又仲裁，天然偏向自己的判断；用"三方等权 + 驳回留痕 + 阻断项人工复核"三约束兜底 |
| R5 | **上下文长度** | 主审要读三份原始意见 + 三份投票 + 用例 + 证据包，需确认 `qwen-max` 的实际窗口与输出上限 |
| R6 | **成本无上限但需可观测** | 全量记录 token 与耗时；知识库单次注入上限 15k token 作为第一道闸；成本与预算见 `docs/10` §10 |
| R7 | **纯文本用例解析质量** | 预处理模型拆步骤可能拆错；拆分结果随报告返回供人核对，拆不出则降级为整篇评审 |
| R8 | **检索效果未验证** | 检索黄金集未建前，"模型不行"的判断不可信；先建 ≥100 条查询-知识对（见 08 §5） |
| R9 | **中文关键词检索** | v1 用 trigram + 精确匹配；zhparser 需编译安装，切换前对比检索集指标 |
| R10 | **检索配置漂移** | 检索参数（Top-K、RRF k、rerank 阈值）必须版本化，变更即触发检索回归 |
| R11 | **`test_scope` 维护成本** | v1 只用于"未覆盖已列场景"提示；初期只覆盖 3–5 个高频模块的功能点 |
| R12 | **投票轮成本** | 投票轮增加 3 次调用与输出长度；候选清单需控制条数，避免 token 失控 |
| R13 | **v1 单条范围的预期管理** | 调用方可能期待功能覆盖率；报告固定 `coverage_claims_allowed=false` |
| R14 | **历史缺陷被误用** | 依赖 `evidence_type` + Prompt + 服务端校验；抽检 `historical_bug` 用法 |
| R15 | **审批流程未落地** | `review_decisions` 建了但没人用；上线前确认审批角色与责任人 |
| R16 | **trigram 召回上限** | 长文本/语义改写召回弱于向量；靠检索集对比，不凭感觉切换 |
| R17 | **投票锚定** | 记录初审与投票差异，统计翻转率；材料去来源化后用评测集验证 |
| R18 | **严重级分歧** | 跨两级（blocker vs suggestion）转人工；统计高估/低估率 |
| R19 | **投影漂移** | `issues` 与 `report_json` 定期一致性校验，支持从事实源重建 |
| R20 | **性能门槛未压测** | 先按阶段观测 P50/P95/P99，压测后再写发布门槛 |
| R21 | **知识库同级冲突** | 不自行选择权威规则；冲突证据留档并转 `need_human` |
| R22 | **成立性/严重级被合并** | 两字段独立落库与统计，避免"成立但严重级错"被掩盖 |
| R23 | **报告投影漂移** | 定期校验 `report_json ↔ issues`，投影只读 |
| R24 | **性能目标冲突** | 模型超时与端到端目标先压测再定，不拍脑袋 |
| R25 | **旧客户端仍传 `X-Role`** | 服务端忽略该头；迁移期记录告警，避免误以为已授权 |
| R26 | **候选与投影漂移** | 投票/候选/投影分表后，定期校验 `review_candidates → issues` 回链完整 |
| R27 | **模型验收未完成** | 真实 Model ID 未 `verified` 前，评测结论只能标"待验证" |
| R28 | **提示注入** | 用例/知识库视为不可信数据；输出仍走服务端校验，不执行文本指令 |
| R29 | **校验分层错位** | 硬校验必须在 API 层完成；Worker 返回 422 是设计缺陷 |
| R30 | **候选向量过期** | 候选合并/重建后旧向量残留；按 candidate 级联删除或用 profile 重建 |
| R31 | **claim 证据复杂** | 证据按主张绑定会增加数据量；先用 3–5 个模块验证可维护性 |
| R32 | **8 次调用超时** | 20 分钟是估算，需压测；阶段 Checkpoint 未验证前不承诺恢复 |
| R33 | **模型对照实验缺失** | 未做 A–E 组实验前，不能宣称多模型优于单模型 |
| R34 | **字典漂移** | 枚举在 02/03/11/17 多处维护；改一处必须同步校验脚本 |
| R35 | **claim 聚合复杂** | 证据按主张绑定增加数据与标注成本；先小范围验证可维护性 |
| R36 | **条件仲裁口径** | 跳过仲裁与"主审同意"不同；报告必须写 `arbitration_required=false` |
| R37 | **超时预算未压测** | 20 分钟为估算；阶段超时含重试，需压测校准 |
| R38 | **端到端门槛未验证** | 21 号文档的数字是初始门槛，需用冻结集校准后再作为发布依据 |
| R39 | **跨文档冲突未清完** | 23 份文档仍有字段/枚举/状态差异；冻结前需跑一致性检查脚本 |
| R40 | **三模型价值未验证** | 未完成 A–E 实验前，不能把完整三模型当作既定生产架构 |
| R41 | **审批身份未落地** | 共用 API Key 无法证明审批人；上线前必须接入个人身份 |
| R42 | **指标同名不同义** | 07 与 21 的门槛必须同源；改一处需同步另一处 |
| R43 | **Decision Trace 未实现** | 报告可读性与人工复核效率依赖判断链，需列入 v1 |
| R44 | **Rubric 与文档漂移** | `rubric.yaml` 已落地；CI 必须校验规则 ID、枚举与 Prompt 引用，否则仍会分叉 |
| R45 | **指标改名后的历史数据** | FDR 替代 FPR 后，旧报告指标需重算，不能直接比较 |
| R46 | **生产拓扑未定** | 默认三模型只是候选；A–E 实验前不得写入容量与成本承诺 |
| R47 | **模型未验证** | `unverified` 模型不得进入生产拓扑；接入前逐项实测 |
| R48 | **历史重评缺失** | Rubric/KB 更新后旧报告是否重评需显式触发，不能自动覆盖 |
| R49 | **旧 Worker 写入** | 仅靠 locked_by 不足；fencing_token 未实现前，恢复场景不得上线 |
| R50 | **批量幂等未验证** | force/force_all/部分失败的行为需在 Mock 环境先验证 |
| R51 | **报告 Schema 漂移** | `schemas/report.schema.json` 已落地；旧报告兼容与 Schema 变更需 CI 校验 |
| R52 | **部署/迁移未演练** | 27 号的迁移、备份、回滚流程需在空库与旧库各跑一次 |
| R53 | **真实模型测试成本** | 26 号要求核心测试不依赖真实 API；真实模型只用于验收流水线 |
| R54 | **报告 Schema 多版本** | 旧报告不迁移；渲染器与 API 必须按版本读取，新增字段保持向后兼容 |
| R55 | **预算预留不足** | 核心阶段额度需在任务开始时预留，否则仍会出现"投票没预算" |
| R56 | **附件未实现** | v1 只存引用与指纹；OCR/图片理解不在范围，避免误以为已支持 |
| R57 | **指标改名影响历史** | FDR 与 FPR 不可互换；旧报告指标需重算并标注口径 |
| R58 | **统计功效不足** | 三模型实验样本不足时只能作探索性结论，不能据此冻结架构 |
| R59 | **契约脚本与文档一起漂移** | 检查器和被检查文件同时改错时仍会通过；用 `tests/contract/test_contract_drift.py` 变异测试兜底，脚本变更必须跑全量 |
| R60 | **Verdict 用例与实现脱节** | 实现后可能只跑少量用例；ACC-M0-011 要求全量对照，改 `design/verdict_cases.yaml` 必须同步 `verdict.py` 与 `docs/12` |
| R61 | **参考判定器被误用** | `scripts/verdict_reference.py` 只是规范对照，不是生产实现；`app/` 不得 import，代码评审拦截 |
| R62 | **决策索引覆盖不全** | `design/decisions.yaml` 只索引跨模块契约与门禁相关决策；不得宣称是 docs/08 的全量镜像 |
| R63 | **M0 用例只跑 happy path** | 每条用例必须带失败判定；ACC-M0-017 用变异测试证明检查能失败，不允许"能启动即通过" |
| R64 | **业务范围蔓延** | 新增测试类型、覆盖分析、自动化或审批能力必须先进 `docs/00` 与 BIZ 决策，不能由技术实现悄然扩大职责 |
| R65 | **test_type 误判** | 调用方未显式声明时按 `functional` 处理，可能让非功能用例被误评；报告展示 `test_type`，调用方应显式传值，非功能类型必须被 422 拒绝 |
| R66 | **Rubric 0.2.0 未发布** | 当前为 `draft`，生产加载前必须由 `kb_reviewer` 审核并置 `published`，否则服务端拒绝启动生产模式 |
| R67 | **设计版本被误当产品版本** | `design-v1.6` 只表示设计基线；产品 `product-v1.0` 未交付，对外表述必须写明维度 |
| R68 | **complete 被误读为业务可用** | `complete=true` 只表示流程完整；参与度看 `full_participation`，业务价值看分层验收（docs/08 §5.3） |
| R69 | **兼容模式长期化** | `TEST_TYPE_DEFAULT_POLICY=compat` 只允许过渡期使用，必须有退出时间/版本边界；默认 strict |
| R70 | **供应商可调用≠可外发** | `verification_status=verified` 但 `data_admission_status!=approved` 的模型不得进入生产拓扑 |
| R71 | **四状态混用** | "脚本通过"只到 verified；accepted 必须有验收证据，不得用设计完成或 CI 通过冒充 |
| R72 | **实验后选口径** | A–E 阈值必须在 `experiment_protocol.yaml` 签署前填死，未签署不得启动正式实验 |
| R73 | **台账代替执行** | `execution_plan.yaml` 通过只代表结构自洽；Q/V 项仍需真实决策、实验与验收 |
| R74 | **责任人空位长期化** | `kb_pilot.yaml`/`review_roster.yaml` 的 owner 为空即阻断对应阶段，不能以"待指定"进入试点 |
| R75 | **结构检查被当门禁** | `check_contracts.py` 通过只说明台账自洽；阶段准入必须跑 `check_execution_gate.py --stage` |
| R76 | **阶段依赖倒置** | S2 不得依赖 Rubric 生产发布；生产级证据只能出现在 S4 |
| R77 | **状态覆盖历史** | 状态转换只能追加历史，不得覆盖旧证据；版本变化必须重验 |
| R78 | **统计口径事后调整** | A–E 的样本量/α/异常样本/停止规则必须在协议 signed 前冻结 |

## 6. M0 实现状态与运行方式（2026-11-10）

### 6.1 已实现范围

| 模块 | 实现 |
|---|---|
| 工程骨架 | FastAPI 应用工厂、pydantic-settings 配置（缺 `DATABASE_URL` 快速失败）、structlog JSON 日志、统一错误 envelope、`/livez` `/readyz` `/healthz` `/metrics` |
| 数据层 | PostgreSQL + pgvector Alembic 迁移（`0001_m0_initial`）、幂等部分唯一索引、状态/枚举 CHECK、报告锁定触发器、队列索引 |
| 契约层 | `app.core.enums` 与 docs/17 同源校验；报告 Schema 加载/校验/冻结副本；Rubric 加载、Schema+业务校验、版本绑定、生产拒绝 draft |
| 结论 | `app/pipeline/verdict.py` 唯一入口，36 条真值表用例与参考判定器一致；属性测试、禁止组合、决策字段信任边界 |
| 权限 | API Key 授权表（sha256 摘要）、服务端角色、`X-Role` 仅记录、系统身份不得审批、审批人与提交人分离 |
| 状态机 | 任务/阶段/复核任务迁移校验；租约与 `fencing_token` 条件写入（真实 PG 双 Worker 测试） |
| 流水线 | 输入硬校验/软校验、三路 Mock 盲评、规则分桶融合、独立投票、条件仲裁、服务端结论、报告 JSON + Markdown、人工复核任务 |
| 提交契约 | S1–S7 幂等/代次矩阵（200 重放、202 新建、409 运行中、422 同键不同体）、批量只做聚合、附件内容寻址去重 |

### 6.2 本地运行

```bash
# 1. 依赖（Python >= 3.11）
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"

# 2. PostgreSQL 16 + pgvector（端口 55432）
docker compose -f deploy/docker-compose.yml up -d postgres
export DATABASE_URL=postgresql+asyncpg://testjury:testjury@127.0.0.1:55432/testjury

# 3. 迁移与启动（Mock 模型）
.venv/Scripts/python.exe -m alembic -c alembic.ini upgrade head
.venv/Scripts/python.exe -m app.bootstrap     # 默认需要配置 BOOTSTRAP_API_KEYS

# 4. 测试（无真实模型调用；PG 用例在无数据库时自动跳过）
.venv/Scripts/python.exe -m pytest -q
python scripts/check_contracts.py
python scripts/check_m0_acceptance.py
```

### 6.3 验收边界

- 已回填 `design/m0_acceptance.yaml`：40 条用例 `result=passed`；本地执行环境与时间见文件头。
- **M0 通过只代表工程正确**：不代表评审质量、业务有效性或生产可用（`docs/08` §5.3）。
- 未实现：知识库加载/检索/Rerank、A–E 实验、性能压测、生产部署、恢复演练。
- 真实模型已接入：`REVIEW_MODEL_MODE=live` 时按 `config/models.yaml` 调用 Qwen3.8-Max、DeepSeek-Flash、Kimi-K3.1-Pro；仍为 `testing`，未完成 V-01 正式准入与数据准入。
- `STORAGE_BACKEND=memory` 仅用于单测与本地演示；生产默认 `postgres` 且禁止 memory。
- Rubric 仍为 `0.2.0 draft`：生产模式加载会被拒绝，待 V-03B 审核发布。

### 6.4 设计与实现差异（v1.13 已收口三处）

v1.13 已批准并回写设计：`api_keys` 授权表、附件“内容寻址 + 评审绑定”、`issues` 投影同事务且可重建（D222–D224，见 [变更记录](design/changes/2026-11-10-m1-implementation-gaps.md)）。

仍存在、且**尚未**回写设计的差异：

| 差异 | 现状 | 后续动作 |
|---|---|---|
| 存储适配器实现 | docs/06 列 SQLAlchemy 2.0 ORM；当前实现使用 asyncpg 直连 + Alembic 管理 DDL，语义与约束已由测试覆盖 | M1 前确认：补 ORM 层，或回写 docs/06 的适配器实现口径 |
| 真实模型 | **已接入并跑通**：`qwen3.8-max` / `deepseek-flash` / `kimi-k3.1-pro`（Kimi 指定 pro）；三路盲评与投票全部真实调用，Kimi 按约 3 RPM 限速；仍为 `testing` | V-01 实测报告与数据准入（Q-09）完成后再标 `verified` |
| 知识库检索 | 阶段固定 `skipped`，报告记 `kb_module_missing` | M2/M3 接入 KB、向量、RRF、Rerank |
| CI 远端执行 | `.github/workflows/contracts.yml` 已定义 contract/unit/migration/mock-e2e/ci-all；本地等价命令全部通过，未在 GitHub 远端实际运行 | 首次 push 后确认各 Job 通过 |

### 6.5 M1 前置与真实模型联调

| 能力 | 入口 | 验证 |
|---|---|---|
| 真实评审 | `.env` 设 `REVIEW_MODEL_MODE=live`；模型见 [config/models.yaml](config/models.yaml) | 三路盲评 + 投票真实调用；`TC-LIVE-006`：blind 3/3、vote 3/3、27 次调用 0 失败、成本约 ¥1.04、结论 `need_human`（模型间成立性分歧） |
| 模型连通性 | `python scripts/check_model_connectivity.py` | [evidence/V-01/model-smoke-2026-11-11.json](evidence/V-01/model-smoke-2026-11-11.json) |
| 报告投影 | Worker `finalize_report`：报告字段与 `issues` 同事务写入；ID 由 `uuid5(review_id, issue_no)` 生成 | `tests/m0/test_projection.py`、`tests/integration/test_postgres_e2e.py` |
| 投影重建 | `python scripts/rebuild_projection.py --all [--check]` | `tests/migration/test_projection_rebuild.py` |
| 一致性检查 | `python scripts/check_consistency.py [--review <id>]` | 同上；漂移退出码 1 |
| 附件绑定 | 上传 → `case.attachments[]` 引用校验（存在/摘要/归属）→ 报告展示（`analyzed_by_ai=false`）→ 删除评审级联绑定 | `tests/m0/test_attachments.py` |
| 模型适配器 | `app/llm/base.py` 协议；`registry.py` 注册表校验；`adapters/` OpenAI 兼容 Chat/Embedding + HTTP Rerank；`retry.py` 仅重试可重试错误 | `tests/unit/test_model_registry.py`、`tests/unit/test_llm_adapters.py`（MockTransport，无供应商调用） |

> `.env` 的 `REVIEW_MODEL_MODE=live` 走真实模型；单测/CI 默认 `mock`，不调用供应商。

## 7. 首个测试项目：TestLab Arcade 一期

项目资料已接入仓库：

| 资产 | 位置 |
|---|---|
| 一期策划案（需求/功能） | [kb_content/TestLab-Arcade/requirements.md](kb_content/TestLab-Arcade/requirements.md) · [原件](data/projects/testlab-arcade/source/requirements.md) |
| UI 前端设计规范 V1.0 | [kb_content/TestLab-Arcade/ui_spec.md](kb_content/TestLab-Arcade/ui_spec.md) · [原件](data/projects/testlab-arcade/source/ui_spec.md) |
| UI 测试案例 V1.0（55 条） | [data/projects/testlab-arcade/source/ui_test_cases_v1.0.xlsx](data/projects/testlab-arcade/source/ui_test_cases_v1.0.xlsx) |
| 规范化用例（原始字段） | [data/projects/testlab-arcade/cases.json](data/projects/testlab-arcade/cases.json) |
| 可直接提交的评审请求 | [data/projects/testlab-arcade/case_payloads.json](data/projects/testlab-arcade/case_payloads.json) |
| 项目画像/模块统计 | [data/projects/testlab-arcade/project.yaml](data/projects/testlab-arcade/project.yaml) |
| 静态体检记录（非模型结论） | [data/projects/testlab-arcade/static_review.md](data/projects/testlab-arcade/static_review.md) |

- 共 **55 条 UI 用例**：P0 41 / P1 14；模块：全局规范 7、公共首页 6、登录 7、注册 6、登录后主界面 7、三维弹球 10、个人中心 6、响应式与可访问性 6。
- **范围提醒**：这 55 条是 UI 布局/响应式/可访问性用例，不是功能验收用例；当前评审器 v1 只接受 `test_type=functional`，且 Rubric 面向功能用例质量，不能据此判断像素坐标是否符合 UI 规范。
- 当前知识库装载/检索未实现（M2），送审时会降级为 `kb_module_missing`；UI 规范尚未作为检索证据注入。



