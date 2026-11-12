# MiniShop 知识库首批整改记录（2026-11-12）

本轮落实内容契约、来源绑定、治理状态、显式基线和质量校验，并提供离线候选解析。正式知识库仍未发布；本记录不替代业务复审、原始材料交付或 M2 检索验收。

## 已落地的工程改动

- 根目录项目知识库规范进入文档索引，补充与 `docs/11`、`docs/17` 的兼容关系；机器映射为 `design/kb_contract.yaml`。
- `approved → reviewed`，不会自动变成 `published`；项目/模块隔离、别名冲突、重复 YAML 键、元数据和来源版本均由程序检查。
- MiniShop 来源绑定到 `https://github.com/Viver12138/minishop.git` 的完整提交 `e354437069504381f10a54d9c14baed755f3ba56`。Git 中 78 项与旧快照一致；`.gitignore` 变化、`data/minishop.db` 未纳入 Git。原项目的 **80 项来源已全部按旧 SHA-256 核验并归档**，包含原始数据库；快照 ZIP 和内部每个文件都由程序复验。
- 原人工复核工作簿已从用户提供的 `minishop/docs` 取得，受控副本位于 `evidence/M2/manual_review/`。Q/C/G/D 四张业务表共 **77 行、全部列** 与既有 `review_input_rows.json` 完全一致，原表、提取记录和比对结果分别绑定哈希；不新增签名或审核结论。
- 10 项冲突与 15 项问题使用四维状态；原 `resolved/answered/blocking_resolved` 保留为 `legacy_*`，不再解释为实现修复完成。
- `review_policy.yaml` 登记当前实现与目标规格两种不可变基线，无默认选择。离线构建必须显式指定基线。
- 试点及复核责任表切换为 MiniShop `order`，允许先从一个模块开始；实名负责人和黄金集未齐备，仍为 proposed/pending。通用空白模板在 `design/templates/kb_pilot.yaml`。
- 两处重复变更字段合并，HTTP 状态码标签改为字符串；支付规则和测试规范的正文冲突已修订，版本说明补充当前来源后也退回待复审，共三份修订稿。当前为 **21 approved / 16 in_review**。
- 已审核内容建立哈希锁，用于检测后续未经复审的修改；这是导入已有审核快照，不是新增审核。
- `admission.yaml` 按模块和评审类型登记候选范围及限制，正式准入全部保持 blocked。
- CI 聚合检查新增 knowledge 检查；增加针对绕过审核、来源篡改、错误行号和假发布状态的变异测试。

## 重跑方式

在项目环境中运行：

```powershell
python scripts/check_contracts.py
python -m pytest tests/contract tests/unit tests/m0 -q
python scripts/check_kb.py --source-root '<MiniShop 本地仓库>' --json
python scripts/check_kb.py --source-root '<MiniShop 本地仓库>' --release --json
python scripts/build_kb_candidate.py --source-root '<MiniShop 本地仓库>' --baseline current_implementation --output .tmp/minishop-candidate.json
```

MiniShop 本地仓库需保留上述完整提交；校验直接读取该提交的 Git 原始文件，仓库后续新增提交不改变本轮基线。校验不执行 MiniShop 代码，工作目录的临时变化不作为来源证据。来源地址、哈希和行号必须同时匹配。正常检查通过只表示候选资料结构与已声明限制一致；`--release` 当前应返回失败。

## 验证记录

| 检查 | 结果 |
|---|---|
| 聚合契约检查 | 32 项检查通过；两项 Git 差异提示均有完整原快照可供复核 |
| 代码格式与静态检查 | 本轮新增知识库代码和测试通过 Ruff 检查 |
| 原始来源 | 80/80 逐项 SHA-256 一致；归档整体哈希及内部成员均复验通过 |
| Git 来源 | 固定提交的 78 项相同、1 项忽略配置变化、1 项数据库未入 Git，均保留真实记录 |
| 原始工作簿 | Q/C/G/D 共 77 行、全部列与提取记录一致，原表及比对证明哈希复验通过 |
| 契约/单元/M0 回归 | **341 通过，2 跳过**；跳过项需要真实 PostgreSQL，与本轮知识库内容无关 |
| 离线候选 | 两种显式基线各 **21 份文档、125 个片段**；16 份待复审文档被排除 |
| 版本隔离 | 基线变化产生不同构建版本；评审准入范围变化也触发新构建版本，内容版本独立保留 |
| 正式发布门禁 | `--release` 按预期返回 1；没有 active 构建或正式发布 |

机器结果保存在 [`../../evidence/M2/README.md`](../../evidence/M2/README.md)；完整片段候选在本地 `.tmp/minishop-candidate-current_implementation.json` 和 `.tmp/minishop-candidate-target_specification.json`，不作为 active 索引。测试未调用真实模型，也未改动 MiniShop 源码。

### Docker 与数据库补验（2026-11-12）

已开启 Windows 虚拟机平台及 WSL 功能，用户手动重启后安装 WSL 3.0.5.0 并启动 Docker Engine 29.8.1。项目原 Compose 配置未修改；`testjury-postgres` 健康运行，地址 `127.0.0.1:55432`，PostgreSQL 16.15、pgvector 0.8.7。

补跑数据库迁移、真实 PostgreSQL 完整链路、并发写入保护和报告锁定共 **8 项，全部通过，0 跳过**，其中包含上轮因缺数据库而跳过的两项。测试使用新建独立临时数据库，完成后已清理，未清空项目数据库；原 341 通过/2 跳过结果保留为上轮历史。补验记录见 `evidence/M2/docker_postgres_verification.json`。本次未自动重启电脑，也未修改系统 DNS。

## 仍需交付或验证

1. 16 份文档的有权人员复审；旧工作簿不作为三份新修订正文的自动批准。
2. 原始来源已完整保存，后续版本继续保留快照与 Git 差异记录；不能用重新播种数据替代历史数据库事实。
3. MiniShop 代码/配置/原 README 的待办修复与业务回归。绑定的源码提交保留为旧证据，后续修复需绑定新提交及新知识版本。
4. 正式 PRD 的权威性/版本确认、测试资产与冻结的检索/评审黄金集。本机发现 `完整电商平台_业务需求说明书_V1.0.docx`，目前只登记为待核验候选，未直接作为正式业务依据。
5. Embedding、混合索引、检索与评审黄金集验收、线上任务基线冻结、权限控制发布及 active 切换。

本轮候选解析不会改变运行时 `kb-none`。旧的 `_delivery/01`–`08` 和原评审报告保留为各自版本的历史材料，当前状态以本记录、机读治理台账与最新校验结果为准。
