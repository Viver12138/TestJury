# 功能用例人工裁决工作台（functional-only）

> 来源：`functional_test_cases_v1.1.xlsx` 的 57 条可送审功能用例。  
> 本工作台是 **功能线**，与 `../adjudication/`（UI/页面线，8 用例 / 19 候选）完全独立；不要把两边标签混用。

## 当前样本

- 抽样 **15 条**（覆盖公共首页、注册、登录、会话、主界面、游戏、成绩、权限）；
- 生成 **24 条静态预审候选**，全部 `final.validity=pending`；
- **未调用真实模型**：15 条 × 6–8 分钟成本过高；本轮先做静态对照，候选不是模型结论；
- 其余 42 条功能用例尚未抽样。

## 抽样清单

`HOME-001`、`HOME-005`、`REG-001`、`REG-002`、`REG-007`、`LOGIN-001`、`LOGIN-002`、`LOGIN-005`、`DASH-003`、`GAME-001`、`GAME-002`、`GAME-007`、`SCORE-001`、`SCORE-002`、`SEC-001`。

重点样本包括：

- `REG-001/002/007`：服务条款复选框在本期策划案中明确“不实现”，用例却要求勾选 → 规则冲突候选；
- `LOGIN-001`：4 个步骤只有第 1 步有预期，且预期覆盖后续动作 → 步骤/预期错位；
- `HOME-001`：期望展示版本号/运行状态，与策划案 §4.1“本期未展示”冲突；
- `GAME-002`：步骤提到网络中断，预期未覆盖；
- `SCORE-001`：测试数据未给具体分数/时长/球数，无法验证保存值。

## 使用方法

在仓库根目录执行（注意 `--root` 在子命令前）：

```powershell
python scripts\adjudicate.py --root data\projects\testlab-arcade\adjudication-functional list
python scripts\adjudicate.py --root data\projects\testlab-arcade\adjudication-functional show REG-001
python scripts\adjudicate.py --root data\projects\testlab-arcade\adjudication-functional stats
```

裁决字段与流程沿用 [填写教程](../adjudication/填写教程.md)：

- `valid` 必须 severity + category；`invalid/uncertain/needs_spec` 不填 severity；
- 最终 `pass/needs_fix/blocked/uncertain` 要求所有候选已裁决；未完成用 `in_progress`；
- `defect_count` 必须等于 valid 数；
- `adjudicator` 必须是真实身份。

CSV：[adjudication.csv](adjudication.csv)。  
Excel 填写入口：[adjudication.xlsx](adjudication.xlsx)（由脚本生成，带下拉选项；本地填写文件不提交 Git）。  
导入/恢复：

```powershell
# 推荐：在 Excel 下拉表里填写，回收成 CSV
python scripts\adjudication_sheet.py --root data\projects\testlab-arcade\adjudication-functional check
python scripts\adjudication_sheet.py --root data\projects\testlab-arcade\adjudication-functional to-csv

python scripts\adjudicate.py --root data\projects\testlab-arcade\adjudication-functional import-csv --dry-run
python scripts\adjudicate.py --root data\projects\testlab-arcade\adjudication-functional import-csv
python scripts\adjudicate.py --root data\projects\testlab-arcade\adjudication-functional recover-imports
```

## 边界

- 静态候选只覆盖可静态发现的问题，**不保证穷尽**；后续可补模型评审候选，但需另记 `model_review.status`。
- 不要把本工作台的 `valid` 标签直接当作 V-02 已完成：还需覆盖更多功能用例、双人复核与冻结。
- 5 条 NFR 不在本工作台；当前 `test_type=functional` 不接受。
