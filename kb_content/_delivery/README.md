# 交付物导航（_delivery）

本目录存放 TestJury 知识库候选交付的过程与自检材料，不是业务知识正文。

| 文件 | 对应任务交付 | 说明 |
|---|---|---|
| `source_inventory.yaml` | 项目资料清单（机读） | 80 条资料，含分类、行数、SHA-256、证据等级 |
| `01_source_inventory.md` | 资料清单、分类、完整性、缺失、潜在冲突 | 阶段一报告 |
| `02_extraction_matrix.md` | 知识提取映射 | 来源 → 知识 ID、规则覆盖矩阵 |
| `03_quality_report.md` | 知识质量自检报告 | 元数据/枚举/来源/ID/冲突/过期/推断检查 |
| `04_pending_confirmation.md` | 待人工确认清单 | 15 个问题及关联冲突/缺口 |
| `05_build_summary.md` | 知识库建设总结 | 目录结构、交付物映射、下一步 |
| `06_final_report.md` | 最终报告 | 回答任务第 5 节的 6 个问题 |
| `07_audit_report_2026-11-12.md` | 独立审核报告 | 2026-11-12 复核：漂移检测、元数据复验、事实核对、3 项低危整改 |
| `08_review_application_2026-11-12.md` | 人工复核回写报告 | 应用复核表：24 approved / 13 待复审，冲突/缺口/待确认台账更新 |
| `validation_result.json` | 自检原始结果 | 自动校验的机器输出 |
| `../../MiniShop_知识库人工确认清单.xlsx` | 人工确认工作簿 | 7 个 sheet：填写说明、处理总览、待确认问题、知识冲突、知识缺口、文档审核、字典 |

## 相关治理文件

- `../minishop/_governance/knowledge_gaps.yaml`：15 项知识缺口
- `../minishop/_governance/conflicts.yaml`：10 项冲突
- `../minishop/_governance/pending_confirmation.yaml`：15 项待确认
- `../minishop/_governance/release_notes.md`：候选发布记录

## 重跑校验

自动校验脚本未随交付打包（避免把工具混入知识命名空间）。校验逻辑与结果已记录在 `03_quality_report.md` 与 `validation_result.json`；重新校验时至少应检查：

1. YAML Front Matter 必需字段；
2. 枚举合法性；
3. `source_ref` 文件存在与行号范围；
4. ID 唯一性与 `related_ids` 可解析；
5. `status` 与 `reviewer` 的一致性。
