# 全局知识命名空间

本目录对应 TestJury 规范中的 `_global/`，用于存放跨项目复用的全局知识：

- `testing_standards/`：通用测试用例设计规范；
- `review_rubric/`：通用测试评审标准与 Rubric；
- `automation_principles/`：自动化测试通用原则；
- `glossary/`：跨项目通用术语。

## 本批处理方式

本次交付只针对 `minishop` 项目事实知识，**未复制或改写 TestJury 的全局规范**，原因是：

1. 全局知识应由 TestJury 仓库维护，复制到项目知识库会形成第二份事实源；
2. 规范第 17 节要求字段、枚举和生命周期与既有全局数据字典统一，项目侧不应另建一套；
3. 项目测试规范已在 `minishop/testing/project_test_standards.md` 中给出项目特有约定，并显式引用全局规范作为上位依据。

## 使用约束

- 全局知识可以支撑“测试设计质量”类判断（E3），不能替代项目业务规则。
- 不得用通用规范推断 MiniShop 的具体状态、权限或数值约束。
- 若后续需要把全局文档纳入同一检索库，应在 `kb_content/_global/` 下按规范模板建立独立文件，并标记 `project_id: _global`（或 TestJury 统一约定的全局命名空间标识）。
