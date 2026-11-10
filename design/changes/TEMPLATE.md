# 设计变更记录：<变更标题>

- 日期：YYYY-MM-DD
- 设计基线：design-vX.Y → design-vA.B
- 关联决策：Dxxx / BIZ-xxx / Q-xx
- 变更级别：P0 契约 / P1 设计 / P2 局部

## 1. 变更原因

（问题、证据、触发来源；不要只写"优化"。）

## 2. 变更内容

- 变更前：
- 变更后：
- 不改变的部分：

## 3. 影响面

- [ ] 业务规则 / Rubric（`docs/04`、`rubric/`）
- [ ] API 契约（`docs/03`）
- [ ] 数据模型 / 迁移（`docs/02`、`docs/14`）
- [ ] 报告结构 / Schema（`schemas/`）
- [ ] 流程与状态机（`docs/01`、`docs/12`、`docs/13`）
- [ ] 提示词 / 输出校验（`docs/05`、`docs/18`）
- [ ] 知识库（`docs/11`、`docs/16`、`docs/25`）
- [ ] 验收用例 / 测试（`design/m0_acceptance.yaml`、`tests/`）
- [ ] 人工复核 / 审批 / 身份（`docs/09`、`docs/10`）
- [ ] 历史报告兼容 / 数据迁移
- [ ] 需要重跑检索或模型实验

## 4. 版本变更

| 维度 | 变更 |
|---|---|
| 设计基线 | design-vX.Y → design-vA.B |
| 产品版本 | 不变 / product-vX.Y |
| Rubric | 不变 / x.y.z → a.b.c |
| 报告 Schema | 不变 / report-x.y |
| 知识库 | 不变 / kb-<hash> |

## 5. 回归与证据

- `python scripts/check_contracts.py`：
- `python -m pytest tests/contract -q`：
- 其他专项测试 / 评测：
- 未验证项及原因：

## 6. 批准

- 负责人：
- 批准时间：
- 备注：
