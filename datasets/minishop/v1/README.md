# MiniShop 种子黄金集 v1

固定源码提交：`e354437069504381f10a54d9c14baed755f3ba56`。评审基线为 `current_implementation`。

- `retrieval.jsonl`：18 条检索样例，其中包括跨项目、跨模块和无答案隔离样例。
- `review.jsonl`：30 条用例，15 个场景族，每族包含正确预期和单项错误预期。
- `manifest.json`：文件校验值、来源、授权与标注身份。按场景族分组，正反例不能跨集合。

标注者是用户授权的 `codex-delegated-reviewer`。这是代理编写并复核的种子集，不是独立人工双盲黄金集；已有全部集合的检索结果曾用于诊断，`frozen` 名称不构成未见过的盲测证明。内容未因模型误报而改成迎合模型的标签。

检索验收要求各集合 Recall@10 至少 0.8，且所有负例均不返回证据。该门槛只验证检索，不能证明完整评审效果。

真实模型评测保留原始报告、调用错误、版本和分类匹配结果。分类匹配只是诊断指标，需要进一步检查问题语义、重复问题、严重级和证据支持。Mock 结果仅验证流程。

重跑：

```powershell
.\.venv\Scripts\python.exe scripts/prepare_knowledge_release.py --baseline current_implementation
.\.venv\Scripts\python.exe scripts/evaluate_review_gold.py --mode live --topology dual --split dev --limit 6
```

修改标签必须新建数据版本；保留旧文件及对比依据。反馈不会自动写入黄金集。
