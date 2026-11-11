# 人工裁决工作台（TestLab Arcade）

> 目的：把 AI 评审/静态审计产生的候选问题，转成**人工裁决**的 issue 级标签。
> 状态：所有 `final.validity` 当前为 `pending`；在人工填写并签名前，不得作为 ground truth、训练标签或验收依据。
> **填写教程：[填写教程.md](填写教程.md)**（含 Excel/CSV 与 YAML/CLI 两条路线、判定树、示例、常见错误）。

## 文件

- 每个用例一个 YAML：`<case_id>.yaml`
- 汇总表：`adjudication.csv`（可直接用 Excel 打开填写；若缺少 `case_verdict` 等列，先关闭 Excel 再执行 `python scripts/adjudicate.py export-csv` 重新生成）
- 用例快照：`cases.json` / `case_payloads.json`

## 裁决字段

| 字段 | 取值 | 说明 |
|---|---|---|
| `final.validity` | `valid` / `invalid` / `uncertain` / `needs_spec` | 问题是否成立；`needs_spec` 表示规范未定义、需产品确认 |
| `final.severity` | `blocker` / `major` / `suggestion` / `null` | 仅 valid 时填写 |
| `final.category` | Rubric 分类 | 如 预期不明确、不可重复、步骤不可执行 |
| `final.correction` | 文本 | 建议如何改写用例 |
| `final.adjudicator` | 人名/身份 | 必须填写，不能用 AI 代替 |
| `final.adjudicated_at` | ISO 时间 | 裁决时间 |
| `case_level.verdict` | `in_progress` / `pass` / `needs_fix` / `blocked` / `uncertain` | 用例级结论；最终结论要求无 pending 候选 |
| `case_level.defect_count` | 整数 | 必须等于 valid 候选数；可留空自动计算 |

## 流程

1. 人工阅读 YAML 中的用例快照、候选 claim、证据与 AI 建议；
2. 在 `final` 中填写裁决，在 `case_level` 填写用例结论；
3. 用 `python scripts/adjudicate.py decide ...` 或直接编辑 YAML/CSV；
4. 运行 `python scripts/adjudicate.py stats` 查看进度；
5. 全部裁决完成后，才可导出为评测集或缺陷清单。

## 当前样本

- UI-GAME-007：真实三模型评审，8 条原始问题去重为 6 条候选；
- UI-LOGIN-006、UI-REG-005、UI-PROFILE-004、UI-RESP-002、UI-RESP-006、UI-HOME-005、UI-GLOBAL-005：静态比对候选，待人工裁决（可补真实模型评审）。
- 分类修正：这 8 个用例全部属于 **UI/页面用例**；早先分类版把其中 3 个标成“功能测试”是错误口径。当前 19 条候选不应计入 functional 评测标签。功能用例以 `functional_test_cases_v1.1.xlsx` 为准，详见 [classification.md](../classification.md)。

> AI 建议只是线索，不是标签；`likely_valid` 也不等于 valid。
