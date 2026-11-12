# 交付物导航（_delivery）

本目录存放 TestJury 知识库候选交付的过程与自检材料，不是业务知识正文。

2026-11-12 后续开发已加入用户授权的 AI 技术复核和本地运行知识库；最新范围、证据与限制见 `docs/development-2026-11-12.md`。下面各报告保留其生成时的历史状态。

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
| `09_contract_remediation_2026-11-12.md` | 首批整改记录 | 当前状态、契约/证据/治理/基线、重跑方式与剩余发布条件 |
| `source_binding.yaml` | 不可变来源绑定 | 仓库/完整 commit/快照与仓库哈希、受控人工决策及内部规范 |
| `validation_result.json` | 自检原始结果 | 自动校验的机器输出 |
| `../../evidence/M2/manual_review/MiniShop_知识库人工确认清单_复核修正版.xlsx` | 原人工确认工作簿 | 四张业务表 77 行与原提取记录逐项一致；原表及比较结果受控保存 |

## 相关治理文件

- `../minishop/_governance/knowledge_gaps.yaml`：15 项知识缺口
- `../minishop/_governance/conflicts.yaml`：10 项冲突
- `../minishop/_governance/pending_confirmation.yaml`：15 项待确认
- `../minishop/_governance/release_notes.md`：候选发布记录

## 重跑校验

当前检查入口为 `scripts/check_kb.py`（已纳入 `scripts/check_contracts.py`），离线解析入口为 `scripts/build_kb_candidate.py`；工具保留在代码目录，不混入业务知识。旧 `03_quality_report.md` 与 `validation_result.json` 是原交付快照，不能代表本轮已满足发布要求。当前检查包括：

1. YAML Front Matter 必需字段；
2. 枚举合法性；
3. `source_ref` 文件存在与行号范围；
4. ID 唯一性与 `related_ids` 可解析；
5. `status` 与 `reviewer` 的一致性。
