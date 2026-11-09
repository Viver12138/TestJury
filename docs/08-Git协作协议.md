# 08 · 提交与推送协议（Git 协作规范）

> **范围**：`https://ngitlab.testplus.cn/songjiahao/testjury.git` 上的多人协作提交与推送约定。
> **原则**：`main` 永远可发布；每一次提交都自包含、可回滚；不在受保护分支上 force push。
> **状态**：生效 · 2026-11-09

---

## 1. 总则

1. **`main` 是唯一权威分支，始终可部署**。任何破坏 `main` 的操作（测试红、构建坏、依赖缺失）视为事故。
2. **不在 `main` 上直接开发**。所有改动经功能分支 + Merge Request（MR）合入。
3. **提交要小、独立、语义清晰**。一个提交只做一件事，方便 `revert` 和 `bisect`。
4. **文档与代码同等对待**。`docs/`、`kb_content/` 的改动同样走功能分支 + MR。

## 2. 分支模型

采用 **主干开发 + 短生命周期功能分支**（团队 ≤ 5 人，不引入 Git Flow）：

| 分支 | 作用 | 生命周期 | 谁可以写 |
|---|---|---|---|
| `main` | 权威、可发布分支 | 永久 | 仅通过 MR 合入，禁直接 push |
| `feat/*` | 功能开发分支 | 任务完成即删 | 开发者本人 |
| `fix/*` | 缺陷修复分支 | 修复合入即删 | 开发者本人 |
| `docs/*` | 文档/知识库改动分支 | 合入即删 | 任何人 |
| `chore/*` | 依赖、构建、脚本等杂项 | 合入即删 | 任何人 |

> 当前没有 `dev` / `release` / `hotfix` 分支，除非项目规模增长后再评估。

## 3. 分支命名

```
<type>/<简短描述>
```

- `type`：`feat` `fix` `docs` `chore` `refactor` `perf` `test`
- 用连字符 `-` 分隔单词，全小写，不用中文、不用大写
- 描述要能说明意图：`feat/kb-retrieve-context`, `fix/verdict-server-authority`, `docs/git-collab-protocol`

创建新分支：
```bash
git checkout main
git pull origin main            # 先同步到最新
git checkout -b feat/kb-retrieve
```

## 4. 提交规范（Conventional Commits）

提交信息采用 `<type>(<scope>): <subject>` 格式。

**type（必填）**

| type | 用途 | 示例 subject |
|---|---|---|
| `feat` | 新功能 | `feat: 接入知识库检索上下文组装` |
| `fix` | 缺陷修复 | `fix: 仲裁输出缺项时补齐 need_human` |
| `docs` | 仅文档改动 | `docs: 补充融合阈值说明` |
| `refactor` | 重构，无行为变化 | `refactor: 结论计算抽到 verdict.py` |
| `perf` | 性能优化 | `perf: 缓存 embedding 结果` |
| `test` | 测试改动 | `test: 新增融合同义合并用例` |
| `chore` | 构建/依赖/工具链 | `chore: 升级 fastapi 到 0.115` |
| `build` | 构建配置 | `build: 补充 Dockerfile` |
| `ci` | CI 配置 | `ci: 增加 lint 阶段` |

**scope（可选但推荐）**：`api` `db` `pipeline` `kb` `llm` `prompt` `core` `docs`，对应 06-工程结构.md 的目录。

**subject（必填）**
- 祈使句、≤ 72 字符、小写开头（中文内容不受此限）
- 说明"做了什么"，不写"做了什么 和 为什么"，为什么放 body

**body（可选）**
- 空行后写为什么改、影响面、关联 issue/MR 编号
- 需要 `revert` 的关键决定务必写明原因

## 5. 提交信息模板与示例

模板：
```
<type>(<scope>): <subject>

<为什么这么改 / 影响面 / 关联 #issue>
```

好的示例：
```
feat(pipeline): 增加 stage 状态实时落库

处理进程重启时把 processing 任务重置为 queued，
最多重试 1 次避免死循环。见 #42。
```

```
fix(verdict): 模型输出 verdict 不再被直接信任

服务端 verdict.py 重算为准，不一致时记日志并覆盖，
作为防止仲裁模型"凭感觉给结论"的最后一道闸。
```

避免的写法：
- ❌ `update file`（无 type、无意义）
- ❌ `fix bug`（不说清楚修了什么）
- ❌ `改一下`（中文不描述意图）
- ❌ 一个提交里混入 `feat` + `fix` + `chore`（拆分）

## 6. 推送协议

### 6.1 推送前自检
```bash
# 1. 只暂存本次要提交的文件
git add <具体文件>            # 不用 git add -A 无脑全加
git status                    # 确认暂存内容

# 2. 本地验证
git commit -m "feat(...): ..."
git pull --rebase origin main  # 先把 main 的更新叠到自己上面（见 7）
git push origin <branch>
```

### 6.2 推送纪律
- **推送到自己的功能分支**随时可以；**永远不直接 push `main`**。
- 推送前务必 `git pull --rebase origin main`，让分支基于最新 `main`，减小冲突。
- 合入 `main` 一律走 MR，不做 `git push origin main`。

### 6.3 禁止事项
- ❌ 禁止 `git push --force` / `-f` 到 `main`（GitLab 已配置受保护分支拦截，也不要去仓库设置里放开）。
- ❌ 禁止 `git push --force` 到**共享**功能分支（别人的工作会被悄悄覆盖）。
- ❌ 禁止 `git add -A` 后不检查直接提交（可能带入 `.env`、密钥、构建产物）。
- ❌ 禁止把 `.env`、`*.pem`、`data/` 下的敏感/大文件提交进库。

## 7. 冲突处理

### 7.1 更新分支（优先 rebase，保持历史线性）
```bash
git fetch origin
git rebase origin/main
# 解决冲突后：
git add <已解决文件>
git rebase --continue
git push --force-with-lease origin <branch>   # 仅对自己的功能分支可用
```

### 7.2 与同伴的分支冲突
- **先沟通后解决**，不要单方面覆盖同伴的提交。
- 用 `--force-with-lease`（而不是 `--force`）做功能分支的强推：只有本地上游指针与远程一致时才允许，避免误伤他人新提交。
- 无法达成一致时，找负责人仲裁，禁止互相覆盖。

## 8. Merge Request（MR）流程

1. 功能分支 push 到远程后，在 GitLab 发起 MR 到 `main`。
2. **MR 标题**用与提交一致的 `<type>(<scope>): <subject>`。
3. **MR 描述**必须包含：改了什么、为什么、验证方式、风险点。
4. **必须通过**：CI（lint + 单测 + 集成测试）+ 至少 1 名他人 Review。
5. Review 意见用 `suggestion`/`comment` 解决后重新 push（`--force-with-lease` 允许用于功能分支）。
6. 合入方式：**Squash merge**（保持 `main` 历史简洁），或 **Rebase merge**（保留提交粒度）——团队统一选一种，建议 Squash。
7. 合入后**立即删除源分支**。

### MR 最小清单
- [ ] 有配套测试（bug 修复先写复现测试）
- [ ] CI 全绿
- [ ] 至少 1 人 Review 通过
- [ ] 涉及 `kb_content` / `rubric` / `prompt` 时，备注版本号会变更（见 10）
- [ ] 没有提交 `.env` 或敏感文件

## 9. 受保护分支与 force push

- GitLab 已将 `main` 设为**受保护分支**，直接 push 和 force push 都会被 pre-receive hook 拒绝。
- 不要为了省事去仓库设置里解除 `main` 保护。
- 需要重写已合入 `main` 的历史（如误提交敏感信息）时，**禁止自行 force**，联系仓库管理员评估（一般用 `git filter-repo` + 管理员授权操作）。

## 10. 知识库 / 文档 / Prompt 的提交约定

这些内容影响线上评审质量与版本追溯，改动要更谨慎：

| 内容 | 位置 | 特殊要求 |
|---|---|---|
| 知识库源文件 | `kb_content/` | 合入后 `kb_version` 变化，需在 MR 说明；先小步改、跑通再扩 |
| 评审标准 rubric | `rubric/rubric.yaml` | 改动需评审团队确认，注明影响哪些结论档位 |
| Prompt | `app/prompts/*.jinja2` | 每个文件独立 `prompt_version`，MR 备注版本号变更 |
| 设计文档 | `docs/*.md` | 与代码同行，改契约/数据模型时同步更新对应文档 |
| 验收/黄金集 | `data/golden/` | 标注类数据，人工复核后回写，禁止擅自改标签 |

> 触发版本号变化（`kb_version` / `rubric_version` / `prompt_version`）的改动，MR 描述里必须写清"旧版本号 → 新版本号"及影响。

## 11. 紧急修复路径

生产 `main` 有问题时：
1. 从 `main` 开 `fix/xxx`（不要从旧功能分支改）。
2. 写复现测试 → 修复 → CI → 紧急 Review（可放宽到 1 人）。
3. 合入 `main` 后**立即补上完整回归**（见 07-验收与回归.md），再补正式 Review。

## 12. 命令速查

```bash
# 新建功能分支
git checkout main && git pull origin main
git checkout -b feat/xxx

# 日常循环
git add <文件>
git commit -m "feat(scope): subject"
git pull --rebase origin main
git push origin feat/xxx

# 解决冲突后继续 rebase
git add <文件> && git rebase --continue

# 功能分支强推（仅对自己）
git push --force-with-lease origin feat/xxx

# 查看待提交/待推送
git status
git log --oneline origin/main..HEAD
```
