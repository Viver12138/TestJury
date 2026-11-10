# TestJury Schemas

> 机器可执行契约：报告 JSON Schema。Rubric 见 `rubric/`；枚举语义见 `docs/17`。

| 文件 | 用途 |
|---|---|
| `report.schema.json` | 报告 JSON 结构（`report_json`）的唯一 Schema |
| `README.md` | 本说明 |

## 规则

1. 报告生成后必须通过 Schema 校验；失败不得落库。
2. Schema 变更必须递增 `report_schema_version`，并保留旧版本文件（如 `report-1.1.schema.json`）。
3. 历史报告按生成时的 Schema 读取，不按最新 Schema 强转。
4. CI 必须校验：
   - Schema 自身合法；
   - `docs/03` 响应示例与 Schema 一致；
   - `verdict.py` / `issues` 投影字段均在 Schema 内；
   - 旧版本报告在新代码下仍可读取。

## 版本

| `report_schema_version` | 文件 |
|---|---|
| `report-1.0` | `report.schema.json`；冻结副本 `versions/report-1.0.schema.json` |

## 多版本兼容

- 历史 `report_json` **不自动迁移**；按生成时的 `report_schema_version` 读取。
- 每个版本有独立 Schema 与渲染器；渲染器按版本选择，不按最新模板强转。
- 如需转换，生成新的派生数据，不覆盖原报告。
- 旧版本读取能力至少覆盖承诺的保留周期。
- 新增字段必须向后兼容（旧报告缺字段时渲染器给默认值）；删除/改义字段必须升主版本并保留旧 Schema。
