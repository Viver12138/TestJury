# 最终报告：MiniShop 项目知识库候选交付

> **历史快照**：本报告为 2026-11-11 交付时的结论。2026-11-12 已应用人工复核：**24 份 approved / 13 份 in_review 待复审**，冲突、缺口、待确认台账均已更新；当前状态以 [`08_review_application_2026-11-12.md`](08_review_application_2026-11-12.md) 为准。
>
> 项目：`minishop`
> 依据：`TestJury_项目知识库数据规范_v1.0.md`
> 快照：2026-11-11
> 交付性质：**候选知识库（candidate）**，未正式发布
> 结论先行：**可用于 TestJury 的人工审核流程，不足以支撑正式评审。**

## 1. 当前项目已经具备哪些知识

本批共生成 **37 份知识文档**，覆盖：

| 类别 | 内容 |
|---|---|
| 项目级 | 定位、版本、平台、角色权限、模块清单、环境 |
| 需求 | `order` 模块的预览/创建、模拟支付、发货/收货、取消 |
| 业务规则 | 11 条：金额重算、地址、SKU/库存、用券资格、门槛与应付、下单副作用、取消与券归还、支付金额与重复支付、扣库存/销量、发货与收货、越权边界 |
| 流程/状态 | 下单到确认收货主流程；订单 8 个状态、合法/非法转换、状态不变量 |
| 接口/数据 | 6 个订单/支付/发货接口契约；订单/明细/支付/物流/券/库存/消息表结构、状态枚举、种子数据、测试数据准备 |
| 测试 | 项目测试规范、测试环境、测试数据策略 |
| 自动化 | 现有 `e2e_test.py` 能力、定位/断言约定、自动化限制 |
| 术语/经验 | 业务术语表；交易域代码走查风险线索（E4） |
| 治理 | 15 项知识缺口、10 项冲突、15 项待确认、候选发布记录 |

同时完成了：

- 80 份项目资料的清单化（含 SHA-256、行数、分类）；
- 69 个 OpenAPI operation 的核对；
- 18 张数据库表、24 个索引、种子数据的核对；
- 37 份文档、86 个行号锚点的自动校验：**0 错误、0 警告**；
- `e2e_test.py` 在独立库上 48/48 通过（仅证明当前实现行为，不代表业务正确）。

## 2. 哪些知识可以进入 TestJury 审核流程

**37 份知识文档都可以进入“审核流程”**，因为：

- 元数据完整；
- 来源可定位（文件存在、行号范围有效）；
- 无重复 ID/正文；
- 冲突、缺口、待确认已显式登记；
- 未把推断伪装成 E1。

其中可信度相对较高、适合优先审核的：

1. `INTERFACE` 7 份：直接对应代码路由、Schema、表结构；
2. `PROJECT` 5 份：项目定位、版本、平台、角色、环境可由仓库核对；
3. `TEST_SPEC`/`AUTOMATION` 6 份：环境与实际启动、脚本行为可复现；
4. `STATE-ORDER-001`、`FLOW-ORDER-001`：状态赋值点和页面路径可核对。

需要更谨慎审核的：

- `REQUIREMENT` 4 份：没有 PRD，是 README + 代码反推；
- `BUSINESS_RULE` 11 份：是当前实现行为，不等于产品意图；
- `EXP-ORDER-001`：E4，只能作为风险线索。

> 注意：按规范，`in_review` 不进入正式评审候选集。这里的“可进入审核流程”指可供人工逐条审核，不等于“已可用于正式评审”。

## 3. 哪些知识仍然缺少证据

| 缺失证据 | 影响 |
|---|---|
| 正式 PRD / 需求规格 / 验收标准 | 需求的“意图正确性”无法确认，只能确认“实现行为” |
| 业务负责人审核记录 | 没有 E1，规则不能作为强制业务事实 |
| 项目测试规范/测试策略 | `testing/` 是整理稿，不是项目已批准制度 |
| 测试用例库、检索黄金集、评审黄金集 | 无法做检索回归、K0/K1 对照 |
| 缺陷系统/历史缺陷/根因 | 无法判断风险是否已修复、是否复发 |
| Git 仓库/commit/tag | 知识版本只能靠快照日期和文件哈希追溯 |
| UI 设计稿/交互规格 | 页面预期与 UI 自动化缺少权威依据 |
| 非功能需求 | 超卖、金额精度、并发、安全无法判定是否违规 |
| 非交易模块的完整资料 | `after_sales`、`review`、`admin` 等只有零散代码事实 |

对应的 15 项缺口见 [`../minishop/_governance/knowledge_gaps.yaml`](../minishop/_governance/knowledge_gaps.yaml)。

## 4. 哪些业务规则需要人工确认

**10 项阻塞确认**（`blocking=true`）：

| 问题 | 需要确认的规则 |
|---|---|
| Q-01 | “立即购买”是直接结算还是加购后跳购物车？ |
| Q-02 | 下单是否预占库存？支付时库存不足应失败还是继续？超卖是否可接受？ |
| Q-03 | 下单成功后是否清空购物车？ |
| Q-04 | 已发货/已完成订单退款被拒后，应回到 `PAID`、`SHIPPED` 还是 `COMPLETED`？ |
| Q-05 | 多支付记录时，订单详情展示哪一条？ |
| Q-06 | 优惠券 `total_quantity` 限制发放还是限制使用？ |
| Q-08 | `PENDING_SHIPMENT` 是启用还是删除？ |
| Q-10 | 单规格商品详情页无法加购是否为已知缺陷？ |
| Q-12 | 待支付订单是否需要超时自动关闭？ |
| Q-15 | 1.0.0 的发布日期、变更、Git commit 是什么？ |

**5 项非阻塞确认**：Q-07 券 `start_time`、Q-09 Dashboard 销售额口径、Q-11 空物流信息、Q-13 Docker `seed_media` 修复方式、Q-14 商品图 SVG 修复方式。

详见 [`../minishop/_governance/pending_confirmation.yaml`](../minishop/_governance/pending_confirmation.yaml) 与 [`04_pending_confirmation.md`](04_pending_confirmation.md)。

## 5. 哪些资料需要项目负责人补充

优先级从高到低：

1. **正式 PRD/需求规格/验收标准**（至少覆盖 order 模块）；
2. **业务负责人对 4 份需求、11 条规则的逐条确认**，并给出 `reviewer`/`reviewed_at`；
3. **项目测试规范/测试策略**，或明确引用 TestJury 全局规范；
4. **真实测试用例**与人工标注的**检索黄金集/评审黄金集**；
5. **缺陷系统或历史缺陷台账**（含根因、修复版本、复发条件）；
6. **Git 仓库/版本标签/发布说明**，用于 `git_commit` 追溯；
7. **UI 设计稿/交互规格**，以及前端测试 ID 约定；
8. **非功能需求**（性能、并发、安全、金额精度）；
9. **Docker 构建修复**（`backend/seed_media` 缺失）与可用的容器测试环境；
10. **独立 API 文档/错误码目录**（当前只有 OpenAPI 自动生成 + 自然语言 message）。

## 6. 当前知识库是否足以支撑 TestJury 开展正式评审

### 结论：**不足以支撑正式评审。**

原因：

- **E1 = 0**：没有任何经业务负责人确认的权威事实；
- **approved = 0（截至 2026-11-11）**：当时 37 份文档全部 `in_review`，按规范被排除在正式评审候选集之外；2026-11-12 复核后为 24 approved / 13 in_review；
- **需求是反推的**：`REQ-ORDER-*` 不是原始 PRD；
- **存在 10 项未裁决冲突**：包括立即购买、超卖、退款状态回退、券发放量、支付展示等；
- **缺少测试用例/黄金集**：无法验证检索质量与评审效果；
- **只有 order 模块**：其他模块的知识缺口会限制跨模块评审；
- **没有 Git 追溯**：无法满足发布记录对 commit 的要求。

### 当前可以支撑什么

- 作为 **TestJury 知识库审核流程的输入**；
- 支撑 **order 模块的规则级人工评审**（前提是审核人按 `source_ref` 回查）；
- 支撑 **测试数据准备、接口断言、状态覆盖**的设计；
- 帮助评审者识别 **知识缺口与冲突**，避免用常识补造规则；
- 作为后续模块知识库的模板和基线。

### 达到“可正式评审”至少需要

1. 业务负责人完成 37 份文档审核，至少把 order 相关文档改为 `approved` 并填 `reviewer`/`reviewed_at`；
2. 解决 10 项冲突（或明确降级范围），回答 10 项阻塞问题；
3. 补充 order 模块的正式 PRD/验收标准；
4. 准备真实测试用例与评审黄金集；
5. 建立 Git/版本发布机制，完成一次检索回归与 K0/K1 对照。

## 7. 本批没有做什么

- 没有修改、覆盖或删除 `Minishop/` 下的任何原始资料；
- 没有把任何文档标记为 `approved`；
- 没有编造 PRD、测试用例、缺陷或业务规则；
- 没有把代码走查风险写成 E1 事实；
- 没有声称 Docker/UI 主流程可用（两者都有已知环境/前端缺陷）；
- 没有执行检索回归或 K0/K1（缺少索引与黄金集）。

## 8. 交付清单

| 交付 | 文件 |
|---|---|
| 项目资料清单 | [`01_source_inventory.md`](01_source_inventory.md)、[`source_inventory.yaml`](source_inventory.yaml) |
| 知识提取映射 | [`02_extraction_matrix.md`](02_extraction_matrix.md) |
| 知识质量自检 | [`03_quality_report.md`](03_quality_report.md)、[`validation_result.json`](validation_result.json) |
| 待人工确认 | [`04_pending_confirmation.md`](04_pending_confirmation.md) |
| 建设总结 | [`05_build_summary.md`](05_build_summary.md) |
| 知识缺口 | [`../minishop/_governance/knowledge_gaps.yaml`](../minishop/_governance/knowledge_gaps.yaml) |
| 知识冲突 | [`../minishop/_governance/conflicts.yaml`](../minishop/_governance/conflicts.yaml) |
| 待确认（机读） | [`../minishop/_governance/pending_confirmation.yaml`](../minishop/_governance/pending_confirmation.yaml) |
| 发布记录 | [`../minishop/_governance/release_notes.md`](../minishop/_governance/release_notes.md) |
| 知识库入口 | [`../README.md`](../README.md)、[`../minishop/README.md`](../minishop/README.md) |
