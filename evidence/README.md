# evidence · 验证与验收证据目录

> 本目录存放 `design/execution_plan.yaml` 中 Q/V 项的证据文件。**证据不是文档描述，而是可复核的产物**。

## 命名约定

```
evidence/<item_id>/<evidence_id>[.md|.json|.csv|.png|...]
```

- `<item_id>`：如 `V-01`、`Q-14`；
- `<evidence_id>`：与 `execution_plan.yaml` 中 `evidence:`/`acceptance_evidence:` 的字符串一致；
- 一个证据 ID 可有不同扩展名，但内容必须对应同一版本。

## 要求

- 证据对应明确的版本（模型/Rubric/数据集/代码 commit）；版本变化后旧证据标失效，不覆盖。
- 不提交密钥、真实用户隐私或未脱敏数据；敏感证据只存路径引用与审计说明。
- 结构检查（CI）只校验字段与引用；`scripts/check_execution_gate.py --stage Sx` 才校验 manifest、哈希、状态历史与阶段出口。
- 证据是否足以支持业务验收仍需人工判断，脚本不能代替。

## 证据 manifest（每个 item 一份）

`evidence/<item_id>/manifest.yaml`：

```yaml
evidence_id: V-01-model-adapter-test
item_id: V-01
evidence_type: test_report
created_at: "2026-11-10T12:00:00Z"
created_by: owner-id
versions:
  code_commit: "<sha>"
  model_id: "<provider/model>"
  adapter_version: "adapter-v1"
  dataset_version: null
artifact:
  path: "evidence/V-01/model-adapter-test.json"
  sha256: "<sha256>"
validity:
  valid: true
  invalidated_by: null
```

门禁校验：字段齐全、`item_id` 匹配、artifact 存在且 SHA-256 一致、`validity.valid=true`、版本非空。证据内容是否支持验收仍需人工判断。

## 状态历史

`evidence/<item_id>/history.jsonl`，每行一条，只追加不覆盖：

```json
{"item_id":"V-01","from":"designed","to":"implemented","at":"2026-11-10T12:00:00Z","actor":"owner-id","reason":"adapter implemented","evidence":["V-01-model-adapter-test"],"versions":{"code_commit":"<sha>"},"invalidates_downstream":false}
```

最后一条的 `to` 必须等于台账当前状态；转换必须符合 `execution_plan.yaml` 的 `state_transitions`。

## 当前状态

目录为空表示尚无任何 V/Q 项进入 implemented/verified/accepted；这与 `execution_plan.yaml` 的 `designed/open` 状态一致。
