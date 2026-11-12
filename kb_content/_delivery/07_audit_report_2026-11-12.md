# 独立审核报告（2026-11-12）

> **时序说明**：本报告反映人工复核回写**之前**的独立审核状态（37 份均 in_review）。回写后状态为 **24 approved / 13 in_review**，以 [`08_review_application_2026-11-12.md`](08_review_application_2026-11-12.md) 为准。
>
> 审核对象：`kb_content/`（MiniShop 知识库候选稿，快照 2026-11-11）
> 审核人：知识库审核（独立复核，未沿用 11-11 自检结论）
> 机读结果：`kb_content/_delivery/_build/audit_2026-11-12.json`
> 审核原则：只读核对；发现即登记；低危准确性问题当场整改并记录 `change_reason`

## 1. 审核方法

1. **快照漂移检测**：对 `source_inventory.yaml` 的 80 条来源重算 SHA-256，与 11-11 快照比对（含 `data/minishop.db`）。
2. **元数据复验**：37 份知识文档的必需字段、枚举、日期、ID 唯一性、`related_ids`、`module_id`、`source_ref` 文件存在性与 86 个行号锚点范围、`status/reviewer` 一致性、正文重复。
3. **治理复验**：`modules.yaml`（12 模块）、`knowledge_gaps.yaml`（15）、`conflicts.yaml`（10）、`pending_confirmation.yaml`（15）解析与 ID 全集（53）。
4. **人工事实核对**：逐条对照 `Minishop/backend/app/**`、`frontend/src/**`、`e2e_test.py`、`README.md` 与当前数据库，覆盖 11 条规则、4 份需求、2 份流程/状态、7 份接口/数据、项目级 5 份、测试 3 份、自动化 3 份、术语与专家经验。
5. **交付一致性核对**：`_delivery/01~06` 的数量、分布、结论与机读结果交叉比对。

## 2. 机器复验结果

| 检查 | 结果 |
|---|---|
| 来源 SHA-256 比对 | 80/80 一致，**漂移 0**（含数据库文件，证明原始资料未被改动） |
| 知识文档 | 37 份，ID 唯一 |
| 行号锚点 | 86 个，全部在文件行数范围内 |
| 元数据错误 / 警告 | **0 / 0** |
| 治理记录 ID | 53（12 模块 + 15 缺口 + 10 冲突 + 15 待确认 + 1 清单 ID） |
| 状态分布 | `in_review` 37，`approved` 0 |
| 证据分布 | E2 30、E3 6、E4 1、E1 0 |

## 3. 人工事实核对（抽样结论）

| 知识断言 | 代码/数据证据 | 结论 |
|---|---|---|
| 校验顺序：数量→SKU→商品→库存，错误码 400/400/400/409 | `orders.py#L46-L56` | 一致 |
| 同 SKU 重复项不合并、可合计超库存 | `orders.py#L46-L58` 逐项校验 | 一致（已作为边界登记） |
| 用券校验顺序与错误消息（不存在/停用/已用/过期/门槛） | `orders.py#L62-L78` | 一致 |
| 门槛按优惠前总额、应付 `max(total-discount,0)` 两位小数 | `orders.py#L76-L84` | 一致 |
| 创建订单不扣库存、不清购物车、不建支付单、不发消息 | `orders.py#L116-L170` | 一致 |
| 取消仅待支付、归还券且 `used_quantity` 下限 0 | `orders.py#L223-L244` | 一致 |
| 支付门禁、`PENDING` 复用、金额改写、`FAILED` 可再成功 | `payments.py#L39-L118` | 一致 |
| 支付成功扣 SKU+商品库存、增销量、写日志、发消息、`operator_id=用户` | `payments.py#L15-L36,L92-L102` | 一致 |
| 发货仅 `PAID/PENDING_SHIPMENT`、物流单 upsert、发消息；确认仅 `SHIPPED`、物流 `DELIVERED`、不发消息 | `admin.py#L156-L178`、`orders.py#L247-L260` | 一致 |
| 越权：详情 403、取消/确认 404、管理接口 403、禁用用户 403 | `orders.py#L201-L260`、`dependencies.py#L13-L58` | 一致 |
| 状态机 8 态、`PENDING_SHIPMENT` 无赋值点、退款拒绝统一回 `PAID` | 全仓库赋值点检索、`admin.py#L241` | 一致 |
| 表结构、索引、无 CHECK 约束、`payments.order_id` 非唯一、明细无外键 | `models.py`、SQLite `sqlite_master` | 一致 |
| 种子基线：9 商品/16 SKU/运动鞋库存 14（黑 2×4、白 1,1,2,2）/4 券及有效期 | `seed.py#L68-L151`、当前库查询 | 一致 |
| 券 `start_time` 不校验、`used_quantity` 仅用券时累加 | `coupons.py#L40-L88` | 一致 |
| 后台库存“缺货”分支不可达、Dashboard 销售额含 `REFUNDED` | `admin.py#L285`、`admin.py#L28-L33` | 一致（已登记 R-09/R-08、C-08） |
| 前端：单规格无法加购、结算依赖 sessionStorage、SVG 非法、无 `data-testid` | `ProductDetail.tsx#L45-L68`、`OrderConfirm.tsx#L21-L24`、`seed.py#L12-L25`、全仓库检索 | 一致 |
| e2e：48 个 `check()`、无退出码、硬编码 URL、`requests` 不在 requirements | `e2e_test.py`、`requirements.txt` | 一致 |
| 交付文档数量（37/15/10/15/86/0/0）与机读结果 | `_delivery/01~06` vs `validation_result.json` | 一致 |

未发现“把实现缺陷写成正确规则”“无来源业务规则”“伪造验证结论”的情况；所有缺陷类事实均以冲突（C-*）、风险（R-*）或未决问题形式登记。

## 4. 审核发现

| 编号 | 严重度 | 发现 | 处置 |
|---|---|---|---|
| F-01 | 低 | `DATA-ORDER-001` 将 `user_coupons.status` 写成含 `EXPIRED` 的存储枚举，未说明 `EXPIRED` 是读取时计算值 | **已整改**：补充“EXPIRED 非存储值”说明（2026-11-12，含 `change_reason`） |
| F-02 | 低 | `DATA-ORDER-001` 券表“当前可用”列随时间失效（券 2 于 2026-11-20 到期），原表未标注快照日 | **已整改**：列名改为“快照日 2026-11-11 可用”，并要求用 `end_time`/接口动态判断 |
| F-03 | 低 | `RULE-ORDER-008` 前置条件遗漏“支付单存在且归属当前用户，否则 404” | **已整改**：前置条件补齐（2026-11-12，含 `change_reason`） |
| F-04 | 低 | 工作区卫生：`Minishop/backend-startup.log`、`Minishop/frontend-startup.log` 为运行时产物且位于项目目录内；`.venv` 为本机重建。二者均不在资料清单（已排除），但可能干扰后续盘点 | **挂起**：服务停止后删除日志或移入 `_delivery/_build/`；`.venv` 属环境不属资料 |
| F-05 | 信息 | 37 份文档全部 `in_review`、`reviewer=null`、E1=0：符合“未审核不发布”，但同时意味着不能进入正式评审候选集 | 符合规范，维持 |
| F-06 | 信息 | 无 Git 仓库，发布追溯只能用 `snapshot-2026-11-11` + 文件 SHA | 已在 GAP-006 与 release_notes 登记，属发布前阻塞 |
| F-07 | 信息 | 人工确认 Excel 位于工作区根目录（`MiniShop_知识库人工确认清单.xlsx`），不在 `kb_content/` 内 | 可接受；`_delivery/README.md` 已给出相对引用 |
| F-08 | 信息 | `test_data_strategy.md` 券基线以“可用至 <日期>”表述，自带失效信息，无需整改 | 核对通过 |

整改后复验：37 文档、86 锚点、**0 错误 / 0 警告 / 0 漂移**。

## 5. 审核结论

1. **数据真实性**：通过。80 条来源与快照零漂移；抽查的业务事实与代码/数据库一致；缺陷与不一致均以冲突/风险登记，未混入规则正文。
2. **规范符合性**：通过。目录、元数据、枚举、来源定位、治理台账符合《TestJury 项目知识库数据规范 v1.0》；3 处低危准确性问题已当场整改并留痕。
3. **治理完整性**：通过。15 缺口、10 冲突、15 待确认齐备且互相引用一致；无未登记的重大矛盾。
4. **可审核性**：通过。每份文档可经 `source_ref` 行号定位回源码；交付文档与机读结果一致。
5. **正式评审就绪度**：**不通过（预期内）**。阻塞项仍是人工侧：业务审核（approved=0）、10 个阻塞问题、10 个冲突裁决、PRD/测试用例/黄金集/Git 追溯缺失。这些已在 Excel 与治理台账中列为人工事项，不属于知识库本身的质量缺陷。

**审核意见**：知识库候选稿质量合格，可提交 TestJury 人工审核流程；在 F-05/F-06 及 Excel 中 10 个阻塞问题完成前，不得用于正式评审。

## 6. 审核产物

- 机读结果：`_build/audit_2026-11-12.json`
- 复验脚本：`_build/audit_validate.py`（可重复执行，含漂移检测）
- 整改记录：`DATA-ORDER-001`、`RULE-ORDER-008` 的 `updated_at=2026-11-12` 与 `change_reason`
