# 设计变更记录：M1 前置实现补齐（issues 投影 / 附件绑定 / 模型适配器契约）

- 日期：2026-11-10
- 设计基线：design-v1.12（**本次不升版**；批准后统一升为 design-v1.13）
- 关联决策：docs/02 §3.22（报告为事实源、issues 为投影）、docs/14 §7（报告不可变与投影一致）、docs/06 §3.6（模型适配层）、docs/03 §1.3（附件）
- 变更级别：P1 设计（实现补齐；含一处新增绑定表）
- 状态：**待批准**（实现已落地，设计文档尚未回写）

## 1. 变更原因

M0 实现与验收过程中发现三处"设计已要求、实现未落地"或"设计未定义、实现必须新增"的缺口：

1. `docs/14` §7 要求 `report_json` 与 `issues` 投影同事务写入，但 M0 只写了报告，投影表为空；
2. `docs/03` §1.3 的附件上传与 `case.attachments[]` 引用需要评审级绑定，`docs/02` 的 `case_attachments` 假定"上传即绑定评审"，与内容寻址去重不兼容；
3. `docs/06` §3.6 要求三类 Adapter 与模型注册表，M0 只有 Mock，真实供应商接入缺少协议层与错误分类。

## 2. 变更内容

- **变更前**：报告写入后无投影；附件只有全局内容寻址记录；模型调用无 Adapter 协议。
- **变更后**：
  - `finalize_report` 在同一事务内更新 `review_jobs` 报告字段并重建 `issues` 投影；新增 `scripts/rebuild_projection.py` 与 `scripts/check_consistency.py`，投影 ID 用 `uuid5(review_id, issue_no)` 保证重建幂等。
  - 新增 `review_attachments` 绑定表（Alembic `0002_m1_review_attachments`）：评审提交时校验附件存在/摘要一致/归属调用方，报告输出 `attachments[].analyzed_by_ai=false`；删除评审级联删除绑定，物理文件保留给其他引用。
  - 新增 `app/llm/base.py`（Chat/Embedding/Rerank/ReviewModel 协议与错误分类）、`registry.py`（注册表校验，不读取密钥值）、`adapters/`（OpenAI 兼容 Chat/Embedding、HTTP Rerank）、`retry.py`（仅重试超时/5xx/429/连接错误）与 `factory.py`。
- **不改变的部分**：报告 Schema、Rubric、Verdict 真值表、API 路径与状态机、知识库设计、M0 验收用例定义；`api_keys` 表仍属 M0 实现补充，另案回写 `docs/02`。

## 3. 影响面

- [x] 数据模型 / 迁移（`docs/02`、`docs/14`）：新增 `review_attachments`；`issues` 投影开始实际写入
- [x] 验收用例 / 测试（`design/m0_acceptance.yaml`、`tests/`）：新增投影、附件、Adapter 契约测试；M0 用例结果保持 passed
- [x] 提示词 / 输出校验（`docs/05`、`docs/18`）：Adapter 截断/输出非法分类，接入后按角色失败处理
- [ ] 业务规则 / Rubric
- [ ] API 契约（响应字段为 Schema 已允许的增量）
- [ ] 报告结构 / Schema
- [ ] 流程与状态机
- [ ] 知识库
- [ ] 人工复核 / 审批 / 身份
- [ ] 历史报告兼容 / 数据迁移
- [ ] 需要重跑检索或模型实验

## 4. 版本变更

| 维度 | 变更 |
|---|---|
| 设计基线 | design-v1.12（未变更；批准后升 design-v1.13） |
| 产品版本 | 不变 |
| Rubric | 不变（0.2.0 draft） |
| 报告 Schema | 不变（report-1.0） |
| 知识库 | 不变（kb-none） |

## 5. 回归与证据

- `python scripts/check_contracts.py`：通过（31 项检查，0 错误）
- `python -m pytest -q`：270 passed（含 PostgreSQL 迁移 0001/0002、投影重建、附件绑定、Adapter Mock HTTP 契约）
- 其他专项：`scripts/rebuild_projection.py --review <id>` 修复漂移；`scripts/check_consistency.py` 可检出清空投影
- 未验证项及原因：真实供应商 Adapter 未接（无 Key/V-01）；CI 工作流未在 GitHub 远端执行

## 6. 批准

- 负责人：待指定
- 批准时间：待定
- 备注：本记录批准前，README §6.4 的"待设计同步"仍然有效；不得对外宣称设计已更新。
