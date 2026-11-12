---
id: AUTO-LIMITATIONS
title: 自动化能力与限制
knowledge_type: AUTOMATION
project_id: minishop
module_id: null
source_type: AUTOMATION_DOC
source_ref: Minishop/e2e_test.py; Minishop/frontend/src/pages/product/ProductDetail.tsx#L45-L77;
  Minishop/frontend/src/pages/order/OrderConfirm.tsx#L19-L62; Minishop/backend/app/seed/seed.py#L12-L25
source_version: snapshot-2026-11-11
product_version:
- 1.0.0
platforms:
- all
evidence_level: E3
status: approved
owner: minishop_project_team
reviewer: codex-delegated-reviewer
created_at: 2026-11-11
updated_at: 2026-11-12
effective_from: null
effective_until: null
reviewed_at: '2026-11-12'
review_cycle_days: 90
tags:
- automation
- limitations
- ui
- flaky
related_ids:
- AUTO-FRAMEWORK
- AUTO-LOCATOR
- EXP-ORDER-001
sensitivity: internal
content_language: zh-CN
chunk_strategy: section
review_status: delegated_review_completed
change_reason: 用户授权 AI 复核：修正 sessionStorage 与脚本退出语义；保留历史签署
---

# 1. 总体结论

- **API 自动化可行度：高**。交易域的核心规则、状态、金额、库存、权限都能通过 HTTP + SQLite 稳定验证。
- **UI 自动化可行度：中低**。没有测试 ID，且存在 2 个会阻断主流程的已知前端缺陷。
- **当前仓库没有可用的 UI 自动化框架**，仅有 `requests` 脚本。

# 2. 框架与脚本限制

| 限制 | 影响 | 规避/建议 |
|---|---|---|
| `e2e_test.py` 的 check() 失败但正常到达末尾时仍退出 0；未捕获异常会非零退出 | 有 FAIL 也可能被 CI 判为成功 | 改造为 pytest，或解析输出并显式 `exit(1)` |
| `requests` 未在 requirements 声明 | 新环境执行脚本失败 | 加入测试依赖或单独 requirements-dev |
| 硬编码 base URL / 端口 | 环境变化即失败 | 用环境变量 |
| 无 setup/teardown | 数据残留、顺序依赖 | fixtures + 独立库 |
| 依赖种子精确值 | 种子变化/日期变化即失败 | 动态查询 |
| 无报告/重试/截图 | 失败定位成本高 | 引入 pytest-html/Allure、失败截图 |

# 3. UI 限制

## 3.1 阻断级

| 缺陷 | 位置 | 对自动化的影响 |
|---|---|---|
| 单规格商品无法加购 | `ProductDetail.tsx#L45-L68`：`currentSku` 仅在已选规格时计算，而单规格商品没有规格可选 | 无法通过详情页购买 iPhone、咖啡等 8/9 个商品；UI 主流程只能选运动鞋，或改用 API 加购 |
| 商品图 SVG 非法 | `seed.py#L12-L25`：`font-family` 引号嵌套破坏 XML，且 data URL 未编码 | 任何“图片可见/加载成功”的断言都会失败；不要以图片为断言点 |
| 结算页依赖 `sessionStorage` | `OrderConfirm.tsx#L21-L24` | 同标签页普通刷新保留商品；新会话或没有 checkout_items 时直达无商品，自动化需先准备结算数据 |

## 3.2 稳定性限制

| 限制 | 影响 | 规避 |
|---|---|---|
| 无 `data-testid` | 文本/类名变更导致定位失效 | 使用角色+文本；建议开发补充测试 ID |
| AntD 动态类名/弹窗 | 选择器脆弱 | 使用 `.ant-*` 语义类与可见文本 |
| React 异步加载 | 断言早于渲染 | 等待网络响应或元素可见 |
| 消息 Toast 自动消失 | 断言窗口短 | 优先后端消息接口/DB，不依赖 Toast |
| 单页应用路由 | 刷新/直达需要服务器回退 | 本地 Vite 已处理；Nginx 需 `try_files` |
| 金额浮点 | 字符串比较易失败 | 数值容差断言 |

# 4. 数据与环境限制

| 限制 | 影响 | 规避 |
|---|---|---|
| 无重置 API | 用例间数据污染 | 独立库/独立用户 |
| 无删除订单/用户接口 | 无法清理 | 重建库 |
| 券有效期相对播种时间 | 跨日期失败 | 动态查询券状态；后台建券 |
| SQLite 单写者 | 并发用例不稳定 | 串行复核、独立库 |
| 无时钟控制 | 过期/超时场景不可精确构造 | 后台建券指定时间；或直接改库（需谨慎） |
| Docker 构建失败 | 无法用容器环境回归 | 本机 venv 环境 |
| 无 `/health` | 启动探活需用 `GET /` | 用根接口 |
| CORS 白名单固定 | 非 3000/8000 来源的前端调用被拒 | 使用同源代理或改配置 |

# 5. 业务限制（自动化断言需注意）

| 限制 | 影响 |
|---|---|
| 下单不占库存 | 并发/超卖用例不能假设“先下单者一定买到” |
| 支付不校验库存 | 第二笔支付可能成功但库存截断为 0 |
| 订单无幂等键 | 重复提交会产生多张订单，不能断言“只创建一张” |
| 下单不清购物车 | 不能断言购物车已清空 |
| 多支付记录/单对象关系 | 订单详情的 `payment` 可能不是最新一笔，断言需明确 |
| 退款拒绝回 `PAID` | 已发货/已完成订单退款被拒后状态丢失，不能断言恢复原状态 |
| Dashboard 销售额含退款单 | 统计断言需先确认口径 |
| 商品编辑全量替换 SKU | 更新商品可能使购物车/订单明细的 SKU 引用悬空 |

# 6. 不可自动化或成本过高的场景

- 真实支付渠道、支付回调、银行对账；
- 真实物流轨迹、签收推送；
- 短信/邮件/IM 通知；
- 多浏览器兼容性与移动端布局；
- 秒杀级并发与性能压测；
- 服务器故障、网络分区、数据库损坏恢复；
- 定时任务（订单超时、自动确认收货）——当前未实现。

# 7. 建议的自动化优先级

1. **P0 API**：下单金额、库存边界、用券、支付、重复支付、取消、发货、确认、越权；
2. **P1 API**：订单列表/详情字段、支付失败重试、消息、库存日志；
3. **P2 UI**：登录、运动鞋多规格加购、结算、支付、订单详情（避开单规格商品与图片断言）；
4. **P3**：管理后台发货、退款审核。

# 8. 相关示例

- API 断言写法：`AUTO-LOCATOR` 第 2 节
- 环境启动：`TEST-ENV`
- 数据准备：`TEST-DATA`
- 风险清单：`expert_knowledge/order/EXP-ORDER-001.md`

---

## 复核记录（人工复核，2026-11-11）

- **审核结论**：通过
- **审核人**：平台设计者（技术负责人）
- **审核日期**：2026-11-11
- **审核意见**：两个阻断级限制均如实记录且机理与代码一致：单规格无法加购（ProductDetail.tsx:45-50,62-77 currentSku 恒 undefined + seed.py:124 spec_values='{}'，影响 8/9 商品）；SVG data URL 非法（seed.py:19-25 引号嵌套破坏 XML 且未编码）；§5 业务限制逐条对应 payments.py:22,92-102、admin.py:28-33,241,285、models.py:192、products.py:125-143。
- **复核备注**：按 Q-10/Q-14 决策补记修复方向（单规格默认选中 skus[0]；图片改 URL 编码/Base64 或静态文件）；并补充设计者实测的新增限制：种子券时效导致 e2e 脚本中止（见 AUTO-FRAMEWORK）。
- **回写说明**：2026-11-12 已按复核意见回写，状态置为 approved。
