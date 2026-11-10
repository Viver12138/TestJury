# TestJury Rubric

> 机器可执行评审标准。**唯一事实源**为 `rubric/rubric.yaml`；本目录的 Schema 与版本副本用于校验和追溯。
> 设计说明见 `docs/04`，决策口径见 `docs/12`，枚举见 `docs/17`。

## 文件

| 文件 | 用途 |
|---|---|
| `rubric.yaml` | 当前生效的评审规则（唯一加载入口） |
| `schema.json` | 结构校验（JSON Schema 2020-12） |
| `versions/vX.Y.Z.yaml` | 已冻结版本的不可变副本 |
| `README.md` | 本说明 |

## 规则

1. 修改评审标准只能改 `rubric.yaml`，并同步新增 `versions/` 副本；不允许直接改历史版本。
2. `version` 必须符合 `X.Y.Z`；修改规则必须递增版本。
3. `status` 为 `draft` / `reviewed` / `published` / `deprecated`；只有 `published` 版本可被生产加载。
4. CI 必须执行：
   - `schema.json` 校验；
   - 规则 ID 唯一；
   - Prompt 引用的 checkpoint / category / severity 均存在；
   - `docs/04`、`docs/12`、`docs/17` 的关键枚举与 Rubric 一致；
   - 已 `deprecated` 的规则不被生产 Prompt 引用。
5. 规则变更必须触发评审回归（`docs/07` §5）；未通过不得发布。
6. `rubric.yaml` 只描述规则与阈值，不承载模型 Prompt 文本；Prompt 只能引用规则 ID。

## 版本

| 版本 | 日期 | 说明 |
|---|---|---|
| 0.1.0 | 2026-11-10 | 初始草案：三维度检查点、严重级、证据等级、投票与结论规则 |

## 加载与校验

```python
import json, yaml
from jsonschema import validate

rubric = yaml.safe_load(open("rubric/rubric.yaml", encoding="utf-8"))
schema = json.load(open("rubric/schema.json", encoding="utf-8"))
validate(rubric, schema)
```

服务端启动时加载并校验；校验失败拒绝启动（生产）或告警（开发）。报告记录 `rubric_version`。
