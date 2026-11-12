# 本地开发验收证据索引

日期：2026-11-12。授权身份：`codex-delegated-reviewer`（AI 技术复核）。历史人工签署与本轮代理复核分别保存。

| 证据 | 证明范围 |
|---|---|
| `source_snapshots/`、`manual_review/` | 冻结源码归档和原始人工确认工作簿，保留原件 |
| `delegated_content_review.json` | 本轮 17 份知识内容的来源、修订与审核记录 |
| `minishop_gold_source_verification.json` | 用冻结源码、夹具身份和临时 SQLite 执行 15 类黄金集业务事实 |
| `acceptance/` | 不同不可变知识版本的 18 条检索评测，仅代表检索准入 |
| `delegated_verification/` | 独立数据库回归，保留成功与失败记录；最新全套 427 项通过 |
| `local_v4_publication.json` | 无待处理任务时切换检索版本，保留旧知识与报告；范围为本地技术预览 |
| `queue_benchmark/` | 隔离数据库的 Mock 队列并发测量，不包含 HTTP、真实检索与模型耗时 |
| `upgrade_preservation.json` | 备份实际恢复至临时库，升级前后 9 张业务表一致，8 条历史费用回填 |
| `review_eval_live/` | 真实模型运行的原始报告、失败及汇总，以目录内数据集版本、构建版本和代码指纹区分 |
| `review_eval_mock/` | 确定性 Mock 的离线流程检查，不能作为模型效果证明 |
| `delegated_diagnostic_adjudication.json` | 12 条已观察问题的代理逐项复核，区分有效、重复、误报与数据集额外缺陷 |
| `delegated_diagnostic_adjudication_v3.json` | 新版 6 条开发集报告的 12 条发现逐项复核，含范围争议，保留原报告和标签 |
| `delegated_diagnostic_adjudication_dual_full.json` | v3 全量 30 条双模型诊断、36 条发现逐项 AI 复核，含重复、误报与黄金集遗漏 |
| `minishop_gold_source_verification_v4.json` | v4 对应的 15 类业务事实探针，补充购物车数量不变验证 |
| `local_browser/` | Edge 提交、报告下载、历史和反馈检查，以及截图 |
| `container_smoke.json` | 此前镜像、源文件哈希、非管理员运行和健康检查；关闭 Worker 的 Mock 冒烟；本轮质量修复镜像已构建，尚未重新冒烟 |

当前修订黄金集位于 `datasets/minishop/v4`，含 18 条检索和 30 条评审种子；v1/v2/v3 保留以解释修订。v3 有完整双模型诊断，v4 的复测范围以对应结果目录为准。场景族隔离不等于独立盲标，所有版本均明确标注 AI 来源。

完整状态、运行入口与未完成事项见 `docs/development-2026-11-12.md`。原始报告不因反馈而改写；服务身份的反馈不等于人工审批。不能用检索成功、Mock 报告生成或容器健康替代生产效果验收。
