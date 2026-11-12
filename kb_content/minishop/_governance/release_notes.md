# MiniShop 知识库候选发布记录

> Release ID：`minishop-kb-2026-11-12-candidate-02`
> 类型：候选稿（candidate），**未正式发布**
> 日期：2026-11-12
> 项目：`minishop`
> 产品版本：`1.0.0`
> Git commit：**不可用**（工作区不是 Git 仓库）
> 依据：`MiniShop_知识库人工确认清单_复核修正版.xlsx`（2026-11-11 18:11）

## 1. 本次复核回写摘要

| 项 | 结果 |
|---|---:|
| 知识文档 | 37 |
| `approved` | **24** |
| `in_review`（修改后通过，待复审） | **13** |
| 待确认问题已答复 | 15/15 |
| 冲突已裁决（知识级） | 10/10 |
| 知识缺口状态更新 | 15 |
| 元数据/行号锚点 | 0 错误、0 警告；86 锚点 |
| 来源 SHA-256 漂移 | 0/80 |

## 2. 发布范围

| 类别 | 内容 |
|---|---|
| 项目级 | 概览、版本、平台、角色权限、模块清单、环境 |
| 需求 | `REQ-ORDER-001` ~ `004` |
| 业务规则 | `RULE-ORDER-001` ~ `011` |
| 流程/状态 | `FLOW-ORDER-001`、`STATE-ORDER-001` |
| 接口/数据 | `API-ORDER-001` ~ `006`、`DATA-ORDER-001` |
| 测试 | 项目测试规范、测试环境、测试数据策略 |
| 自动化 | 框架概览、定位与断言、限制 |
| 术语/经验 | 术语表、交易域风险线索 |
| 治理 | 知识缺口 15、冲突 10、待确认 15 |

## 3. 来源快照

- 根目录：`Minishop/`
- 文件清单：`kb_content/_delivery/source_inventory.yaml`（80 条，含 SHA-256）
- 盘点报告：`kb_content/_delivery/01_source_inventory.md`
- 无 Git commit；以 `snapshot-2026-11-11` 作为来源快照标识。
- 数据库快照：`Minishop/data/minishop.db`（200,704 字节，18 表，种子数据）。
- 运行态核对：`GET /openapi.json`（69 个 operation）。

## 4. 验证记录

| 验证 | 结果 |
|---|---|
| 来源 SHA-256 与 11-11 快照比对 | 80/80 一致，漂移 0 |
| 元数据/枚举/ID/引用/行号 | 0 错误、0 警告（86 锚点） |
| 后端语法编译 | 通过（28 个 py 文件） |
| 前端 TypeScript 类型检查 | 通过（`tsc --noEmit`） |
| 后端/前端启动与代理 | 通过（8000/3000） |
| `e2e_test.py` | 历史结果 48/48（独立库）；当前种子库因券#1 过期会在 L81 中止，见 `AUTO-FRAMEWORK` |
| 检索回归 / K0/K1 | **未执行**（无索引与黄金集） |

## 5. 当前状态

- 24 份文档：`status=approved`，已填写 `reviewer`、`reviewed_at=2026-11-11`，并追加人工复核记录。
- 13 份文档：`status=in_review`，`review_status=changes_applied_pending_reapproval`，修改已按复核意见回写，待复审后置 `approved`。
- 13 份文档：`PROJECT-ENVIRONMENTS`、`PROJECT-OVERVIEW`、`PROJECT-PLATFORMS`、`PROJECT-ROLES`、`REQ-ORDER-001`、`RULE-ORDER-001`、`RULE-ORDER-002`、`FLOW-ORDER-001`、`STATE-ORDER-001`、`API-ORDER-003`、`TEST-ENV`、`AUTO-FRAMEWORK`、`EXP-ORDER-001`。
- 冲突台账：10 项均 `resolved`（知识级），并标注 `implementation_status`；代码/配置修复仍待执行。
- 待确认台账：15 项均 `answered`，记录结论、确认人、日期与后续动作。
- 知识缺口：8 项 `in_progress`、6 项 `open`、1 项 `downgraded`。

## 6. 仍需完成（正式评审阻塞）

- [ ] 13 份 `in_review` 文档复审并置 `approved`；
- [ ] 代码/配置修复：`CONFLICT-005` Docker seed_media、`CONFLICT-006` 券发放量、`CONFLICT-007` 支付展示、`CONFLICT-009` 单规格加购、`CONFLICT-010` 退款状态恢复、`Q-11` 空物流校验；
- [ ] 原始 README 的目录树、立即购买、Dashboard 口径等文档修正（本次未修改项目原始资料）；
- [ ] `GAP-001` 正式 PRD、`GAP-003` 测试规范、`GAP-004` 用例/黄金集、`GAP-006` Git 追溯；
- [ ] 检索回归与 K0/K1 对照；
- [ ] 将 Release ID 去掉 `candidate` 并登记 Git commit。

## 7. 版本变更策略

- 代码行为变化导致规则变化：新建知识版本，使用 `supersedes`/`superseded_by`；
- 候选-01 保留为历史记录，不覆盖；
- 评审任务必须记录使用的 Release ID；
- 评审执行中不得静默切换版本。

## 8. 历史记录

- `candidate-01`（2026-11-11）：37 份候选稿，全部 `in_review`、0 approved，完成初次自检与独立审核。
- `candidate-02`（2026-11-12）：应用人工复核，24 approved / 13 in_review，冲突与待确认完成知识级闭环。
