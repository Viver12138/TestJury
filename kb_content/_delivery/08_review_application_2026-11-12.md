# 人工复核回写报告（2026-11-12）

> 输入：`MiniShop_知识库人工确认清单_复核修正版.xlsx`（2026-11-11 18:11，人工复核已完整填写）
> 输出：`kb_content/minishop/` 37 份知识文档 + `_governance/` 三本台账 + 发布记录
> 原则：只修改知识库候选文件；未修改 `Minishop/` 下任何项目原始资料

## 1. 复核输入统计

| 工作表 | 条目 | 填写结果 |
|---|---:|---|
| 待确认问题 | 15 | 全部“已处理”，人工结论：接受建议/修改/驳回 |
| 知识冲突 | 10 | 全部给出裁决结论；回写后置 `resolved`，代码/配置修复状态另标 |
| 知识缺口 | 15 | 8 项进行中、6 项待处理、1 项已降级（含 GAP-001/002/003/004/006/012/013/014 等） |
| 文档审核 | 37 | 通过/修改后通过；24 份修改后状态 `approved`，13 份仍 `in_review` |

## 2. 文档回写结果

### 2.1 已批准（24 份）

`PROJECT-VERSIONS`、`REQ-ORDER-002`、`REQ-ORDER-003`、`REQ-ORDER-004`、`RULE-ORDER-003`、`RULE-ORDER-004`、`RULE-ORDER-005`、`RULE-ORDER-006`、`RULE-ORDER-007`、`RULE-ORDER-008`、`RULE-ORDER-009`、`RULE-ORDER-010`、`RULE-ORDER-011`、`API-ORDER-001`、`API-ORDER-002`、`API-ORDER-004`、`API-ORDER-005`、`API-ORDER-006`、`DATA-ORDER-001`、`TEST-DATA`、`TEST-SPEC-PROJECT-001`、`AUTO-LIMITATIONS`、`AUTO-LOCATOR`、`GLOSSARY-001`

处理：`status=approved`、`reviewer` 按复核表填写、`reviewed_at=2026-11-11`、`updated_at=2026-11-12`，并追加“复核记录”章节。

### 2.2 修改后通过、仍待复审（13 份）

`PROJECT-ENVIRONMENTS`、`PROJECT-OVERVIEW`、`PROJECT-PLATFORMS`、`PROJECT-ROLES`、`REQ-ORDER-001`、`RULE-ORDER-001`、`RULE-ORDER-002`、`FLOW-ORDER-001`、`STATE-ORDER-001`、`API-ORDER-003`、`TEST-ENV`、`AUTO-FRAMEWORK`、`EXP-ORDER-001`

处理：`status=in_review`、`review_status=changes_applied_pending_reapproval`、填写 reviewer/reviewed_at，并追加复核记录。**复审通过后才可置 approved。**

### 2.3 已落实的正文修正

| 文档 | 复核意见 | 回写 |
|---|---|---|
| `PROJECT-ENVIRONMENTS` | seed_media 未决与 Q-13 矛盾；SEED_MEDIA_DIR 路径错误 | 改为“已确认删除 Dockerfile#L11 / compose 挂载 / SEED_MEDIA_DIR / config.py#L15”；路径改为 `backend/seed_media`（不存在） |
| `PROJECT-OVERVIEW` | 服务对象含 TestJury 无来源；仅退款被误列为未实现；README 目录树失真 | 改为仅 WHartTest；退款注明“仅退款”语义；补 README 目录树偏差说明 |
| `PROJECT-PLATFORMS` | Swagger 无环境门控；8000 实际对外发布；page_size 上限表述错误 | 改为所有环境暴露；注明 compose 发布 8000；改为上限均 100、默认 10/12 |
| `PROJECT-ROLES` | “修改自己的信息”无接口 | 改为仅查看 `GET /api/auth/me`，并注明无资料修改接口 |
| `REQ-ORDER-001` | address_id 缺失与 0 混淆；补 Q-01/Q-03 | 拆分 VALIDATION_ERROR 与业务 400；补立即购买/购物车连锁限制 |
| `RULE-ORDER-001` | 舍入描述错误 | 改为预览不舍入、落库三金额与小计均 round |
| `RULE-ORDER-002` | address_id 缺失与 0 混淆 | 拆分缺失→VALIDATION_ERROR、0→请选择收货地址 |
| `FLOW-ORDER-001` | 支付 5/6 步被写成两次交互；门槛文案不全；退款拒绝状态 | 补“一次点击连续触发两个请求”；补全文案；补 Q-04 |
| `STATE-ORDER-001` | COMPLETED 被误标终态 | 改为非终态；补 Q-02/Q-04/Q-08/Q-12 决策 |
| `API-ORDER-003` | payment/shipment/refund 缺省非 null；payment 取第一条 | 改为“仅存在时出现（缺省非 null）”；补 SQLAlchemy 实测确定性缺陷 |
| `TEST-ENV` | SEED_MEDIA_DIR 路径；Swagger；seed_media 决策 | 路径修正；Swagger 无门控；Q-13 删除方案 |
| `AUTO-FRAMEWORK` | 未说明 e2e 当前不可执行 | 新增 §1.3：券#1 过期致 L81 StopIteration；退出码恒 0 |
| `EXP-ORDER-001` | 漏发货空值风险；R-06 应升级；待确认需改写 | 新增 R-11；R-06 改为确定性缺陷；补 Q-02/Q-04/Q-06 决策 |
| `API-ORDER-006` | 空物流应拒绝 | 未决问题改为“已确认缺陷待修复”，注明前端已拦截 |
| `DATA-ORDER-001` | 交易域表数 10→11；补 Q-06 | 改为 11 张；补发放总量语义与已确认不一致 |
| `TEST-DATA` | e2e 种子失效 | 补券#1 过期与 L81 StopIteration 提示 |

其余“通过”文档按复核备注补记 Q 决策（写入“复核记录”章节），未改动原有事实陈述。

## 3. 治理台账回写

### 3.1 `pending_confirmation.yaml`

- 15/15 状态 `answered`；
- 新增 `decision`、`decision_note`、`decided_by`、`decided_at`、`follow_up`、`review_note`、`applied_at`、`blocking_resolved`；
- 原问题、建议默认值、阻塞标记保留。

### 3.2 `conflicts.yaml`

- 10/10 状态 `resolved`；
- 新增 `resolution`、`resolution_type`、`implementation_status`、`decided_by`、`decided_at=2026-11-11`、`resolved_at=2026-11-12`、`review_note`；
- 知识级冲突已裁决，但代码/配置修复状态分别标注：
  - `accepted_limitation`：C-02（超卖）、C-04（PENDING_SHIPMENT）、C-08（毛销售额口径）
  - `code_fix_pending`：C-06（券发放量）、C-07（支付展示）、C-09（单规格加购）、C-10（退款状态恢复）
  - `config_fix_pending`：C-05（Docker seed_media）
  - `documented_current_behavior`：C-01（立即购买）
  - `doc_fix_pending`：C-03（README 目录树）

### 3.3 `knowledge_gaps.yaml`

- 15/15 更新：`in_progress` 8、`open` 6、`downgraded` 1；
- 新增 `status_cn`、`owner_role`、`resolution_plan`、`due_date`、`review_note`、`updated_at`；
- 保留原 `risk`、`affected_review_dimensions`、`required_by`。

## 4. 机械复验

| 检查 | 结果 |
|---|---|
| 知识文档 | 37 |
| 状态分布 | approved 24 / in_review 13 |
| ID 唯一 | 37/37 |
| 来源文件存在 + 行号锚点 | 86/86 |
| 元数据错误 / 警告 | 0 / 0 |
| 治理 ID | 53 |
| 来源 SHA-256 漂移 | 0/80 |

> 13 份 `in_review` 仍保留 reviewer 是有意为之：复核已发生，但要求修改后复审；`review_status` 已标记，验证器不再将其视为异常。

## 5. 剩余阻塞

1. **13 份文档复审**：通过后才能进入 `approved` 集合。
2. **代码/配置修复**：C-05/C-06/C-07/C-09/C-10、Q-11 空物流校验仍未改代码；本次只回写知识，未修改 `Minishop/` 原始资料。
3. **原始 README 偏差**：C-01/C-03/C-08 涉及 README 文案，未修改项目原始文件，需项目负责人修订。
4. **资料缺口**：GAP-001 PRD、GAP-003 测试规范、GAP-004 用例/黄金集、GAP-006 Git 追溯仍未关闭。
5. **检索验证**：无索引/黄金集，Recall@10、nDCG@10、K0/K1 未执行。

## 6. 结论

本轮已把 15 个待确认问题、10 个冲突裁决、15 个缺口计划全部回写到知识库候选稿；24 份文档达到 `approved`，13 份完成修改但等待复审。知识库从“全部 in_review”推进到“多数 approved、少数待复审”，但仍**不能整体进入正式评审**，阻塞点在 13 份复审、代码/配置修复和 PRD/测试资产缺口。
