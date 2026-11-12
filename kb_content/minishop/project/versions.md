---
id: PROJECT-VERSIONS
title: MiniShop 版本与适用性
knowledge_type: PROJECT
project_id: minishop
module_id: null
source_type: OTHER
source_ref: Minishop/backend/app/main.py#L11-L15; Minishop/frontend/package.json#L1-L5; Minishop/backend/requirements.txt
source_version: snapshot-2026-11-11
product_version:
  - "1.0.0"
platforms:
  - all
evidence_level: E2
status: approved
owner: minishop_project_team
reviewer: "平台设计者（技术负责人）"
created_at: 2026-11-11
updated_at: 2026-11-12
effective_from: null
effective_until: null
reviewed_at: 2026-11-11
review_cycle_days: 90
tags:
  - version
  - applicability
related_ids:
  - PROJECT-OVERVIEW
  - PROJECT-ENVIRONMENTS
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: approved_after_review
change_reason: "2026-11-12 人工复核回写（审核结论：通过）"
---

# 1. 当前产品版本

| 项 | 值 | 来源 |
|---|---|---|
| 产品/API 版本 | `1.0.0` | `FastAPI(version="1.0.0")` |
| 前端包版本 | `1.0.0` | `frontend/package.json` |
| API 前缀 | `/api` | 各路由 `APIRouter(prefix=...)` |
| 数据库表数 | 18 | `backend/app/models/models.py` |
| 知识快照 | `snapshot-2026-11-11` | 本知识库整理日期 |

# 2. 版本历史

仓库当前只有一个可识别版本 `1.0.0`，没有版本标签、变更日志或数据库迁移记录。

| 版本 | 日期 | 变更摘要 | 来源 |
|---|---|---|---|
| 1.0.0 | 未知 | 初始版本，含前台交易闭环与管理后台 | `main.py`、`README.md` |

`effective_from` 无法从仓库确认，因此本知识库统一填写 `null`，不把“文档整理日期”当作业务生效日期。

# 3. 种子数据版本

- 种子逻辑位于 `backend/app/seed/seed.py`，启动时幂等执行。
- 当前工作区 `data/minishop.db` 的种子数据生成于 2026-09-21（文件时间）。
- 种子数据包含：2 个账号、4 个分类、9 个商品、16 个 SKU、4 张优惠券。
- 种子数据中的优惠券有效期是**相对生成时间**计算的，不同播种日期会得到不同的可领状态。

# 4. 适用性判定

一份知识适用于当前被测版本需同时满足：

1. `project_id = minishop`；
2. `product_version` 包含 `1.0.0`；
3. `status = approved`（本批尚未满足）；
4. 在 `effective_from` 与 `effective_until` 之间；
5. `platforms` 覆盖被测平台。

仅凭 `updated_at` 不能判断规则是否生效。

# 5. 版本变更规则

- 代码行为变化导致规则变化时，应新建知识版本，并用 `supersedes` / `superseded_by` 记录替代关系。
- 旧版本保留用于历史评审复现，但不得进入新版本默认检索范围。
- 每次评审必须记录所用知识发布版本；评审中途不得静默切换。
- 没有 Git 仓库时，至少应在 `_governance/release_notes.md` 记录快照日期与文件清单。

# 6. 已知缺口

- 无正式发布记录、无 Git commit、无 migration 版本；
- 无法从代码判断 1.0.0 的实际发布日期；
- 种子库有效性与播种时间相关，跨环境可能不一致。

> 复核补充（2026-11-11 实测）：当前库券#1「新人满100减10」已于 2026-10-21 自然过期但 `status` 仍为 ACTIVE；seed 幂等不刷新有效期，领券/用券用例执行前须重建库或改用券#2/#3，否则会误判为产品缺陷。

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：版本 1.0.0（main.py:14、frontend/package.json:4）、18 张表、种子基线（2 账号/4 分类/9 商品/16 SKU/4 券）经只读实测 minishop.db 全部吻合；无 .git、无 migration 属实。
- **复核备注**：设计者实测补充（高影响）：库文件播种于 2026-09-21，券#1「新人满100减10」end_time=2026-10-21 已自然过期但 status 仍为 ACTIVE，券#4 为 DISABLED；seed 幂等不刷新有效期 → 领券/用券用例执行前必须重建数据库或改用券#2、#3，否则会误判为产品缺陷。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
