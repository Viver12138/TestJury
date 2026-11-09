# Merge Request 模板（default）

> 标题请遵循提交规范：`<type>(<scope>): <subject>`，如 `feat(pipeline): 增加 stage 状态实时落库`。
> 遵循 [docs/08-Git协作协议.md](../../docs/08-Git协作协议.md) 第 8 节。

## 改了什么

<!-- 一句话说明本次改动的目的与内容 -->

## 为什么改

<!-- 背景、动机；若是修 bug，贴复现步骤与根因；关联 issue/MR 编号 -->

## 影响面

<!-- 涉及哪些模块/目录、会影响哪些已有行为 -->
- [ ] 新增/修改 API（契约文档已同步 `docs/03-API契约.md`）
- [ ] 新增/修改数据模型（DDL 已同步 `docs/02-数据模型.md`）
- [ ] 触发版本号变更（`kb_version` / `rubric_version` / `prompt_version`）

## 版本号变更（如适用）

| 内容 | 旧版本号 | 新版本号 | 影响 |
|---|---|---|---|
| 知识库 `kb_content/` | | | |
| 评审标准 `rubric/rubric.yaml` | | | |
| Prompt `app/prompts/*.jinja2` | | | |

## 验证方式

- [ ] 单测通过（`pytest tests/unit`）
- [ ] 集成测试通过（`pytest tests/integration`）
- [ ] lint 通过（`ruff check`）
- [ ] 端到端演示（`scripts/seed_demo.py`）
- [ ] 人工核验点（如涉及黄金集/标注数据）

## 风险点与回滚

<!-- 失败时如何回滚？是否有不可逆操作（如迁移、改标签） -->

## Checklist

- [ ] 已写好复现/配套测试（bug 修复必须先写测试）
- [ ] CI 全绿
- [ ] 至少 1 人 Review 通过
- [ ] 未提交 `.env` 或敏感文件
- [ ] 已删除源分支（合入后）
