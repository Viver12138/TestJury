"""应用 2026-11-11 人工复核结论：仅修改 kb_content 候选知识，不动项目原始资料。"""
import json, os, re, datetime

ROOT = r"C:\Users\Viver\Desktop\综合电商测试平台demo"
KB = os.path.join(ROOT, "kb_content", "minishop")
ROWS = json.load(open(os.path.join(ROOT, "kb_content", "_delivery", "_build", "review_input_rows.json"), encoding="utf-8"))

by_id = {}
for key, items in (("Q", ROWS["Q"]), ("C", ROWS["C"]), ("G", ROWS["G"]), ("D", ROWS["D"])):
    for it in items:
        if key == "D":
            by_id[it["文档 ID"]] = it

# 找到所有知识文档 id -> path
doc_paths = {}
for dp, dns, fns in os.walk(KB):
    for fn in fns:
        if not fn.endswith(".md") or fn in ("README.md", "release_notes.md"):
            continue
        p = os.path.join(dp, fn)
        text = open(p, encoding="utf-8").read()
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        m = re.search(r"^id:\s*(.+)$", parts[1], re.M)
        if m:
            doc_paths[m.group(1).strip()] = p

errors = []

def set_fm_field(fm, key, value):
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    if pattern.search(fm):
        return pattern.sub(f"{key}: {value}", fm, count=1)
    return fm.rstrip() + f"\n{key}: {value}\n"

def append_review_record(text, row, status):
    marker = "## 复核记录（人工复核，2026-11-11）"
    if marker in text:
        return text
    note = row.get("备注") or "无"
    result = row.get("审核结论") or ""
    reviewer = row.get("审核人") or ""
    opinion = (row.get("审核意见") or "").strip()
    if status == "approved":
        writeback = "2026-11-12 已按复核意见回写，状态置为 approved。"
    else:
        writeback = "2026-11-12 已按复核意见回写；仍为 in_review，待复审后置 approved。"
    record = (
        "\n\n---\n\n"
        f"{marker}\n\n"
        f"- **审核结论**：{result}\n"
        f"- **审核人**：{reviewer}\n"
        "- **审核日期**：2026-11-11\n"
        f"- **审核意见**：{opinion}\n"
        f"- **复核备注**：{note}\n"
        f"- **回写说明**：{writeback}\n"
    )
    return text.rstrip() + record

# 文档级定向修正
TARGETS = [
    ("PROJECT-ENVIRONMENTS",
     "| `SEED_MEDIA_DIR` | `backend/../seed_media` | 预置媒体目录；当前种子图使用内联 data URL，该目录未被实际引用 |",
     "| `SEED_MEDIA_DIR` | `backend/seed_media`（相对 backend 解析，实际不存在） | 无业务代码消费；按 Q-13 决策删除该配置（config.py#L15） |"),
    ("PROJECT-ENVIRONMENTS",
     "在修复前，Docker 部署不能作为可执行环境；评审涉及部署验证时，应登记为环境阻塞而非用例缺陷。",
     "在修复前，Docker 部署不能作为可执行环境；评审涉及部署验证时，应登记为环境阻塞而非用例缺陷。\n\n**已确认处理方式（2026-11-11，Q-13）**：删除 `Dockerfile#L11` 的 `COPY seed_media`、`docker-compose.yml#L9` 的 `./backend/seed_media` 挂载与 `SEED_MEDIA_DIR` 环境变量、`config.py#L15` 的配置；该目录无业务代码消费。修复前容器环境不得作为正式测试环境。"),
    ("PROJECT-ENVIRONMENTS",
     "- `backend/seed_media` 缺失应通过补目录还是删除 `COPY` 修复；",
     "- ~~`backend/seed_media` 缺失应通过补目录还是删除 `COPY` 修复~~ 已确认（2026-11-11，Q-13）：删除相关配置；仅保留“是否提供 /health、版本接口与迁移脚本”和生产安全项为未决。"),
    ("PROJECT-OVERVIEW",
     "MiniShop 是一个轻量级综合电商平台 Demo，作为 WHartTest / TestJury 等测试平台的真实被测系统（SUT）。",
     "MiniShop 是一个轻量级综合电商平台 Demo，作为 WHartTest 测试平台的真实被测系统（SUT）（README.md#L3、main.py#L13）；仓库中没有 TestJury 相关来源。"),
    ("PROJECT-OVERVIEW",
     "- 发票、退货物流、换货、仅退款；",
     "- 发票、退货物流、换货；当前退款为“仅退款”语义（无退货/换货环节，refunds.py#L28-L38）；"),
    ("PROJECT-OVERVIEW",
     "- 本知识库入口：`kb_content/minishop/README.md`",
     "- README.md#L124-L154 目录树与实际不符（components/、router/、database/ 不存在；路由在 App.tsx#L63-L101，数据库为 database.py 文件），引用路径以代码为准。\n- 本知识库入口：`kb_content/minishop/README.md`"),
    ("PROJECT-PLATFORMS",
     "| Swagger | OpenAPI UI | `http://<host>:8000/docs` | 仅开发/测试环境暴露 |",
     "| Swagger | OpenAPI UI | `http://<host>:8000/docs` | 无环境门控，所有环境均暴露（main.py#L11-L15） |"),
    ("PROJECT-PLATFORMS",
     "- 分页：`page` 从 1 开始，`page_size` 有上限（订单/商品不同）。",
     "- 分页：`page` 从 1 开始；订单与商品的 `page_size` 上限均为 100，仅默认值不同（订单 10、商品 12）。"),
    ("PROJECT-PLATFORMS",
     "- Docker：前端 3000 由 Nginx 提供，`/api/` 反代到 `backend:8000`；后端不直接暴露给浏览器。",
     "- Docker：前端 3000 由 Nginx 提供，`/api/` 反代到 `backend:8000`；但 compose 仍将 8000 发布到宿主机（docker-compose.yml#L5-L6），后端直接可达。"),
    ("PROJECT-ROLES",
     "| 查看/修改自己的信息 | ❌ | ✅ | ✅ |",
     "| 查看自己的信息（GET /api/auth/me） | ❌ | ✅ | ✅ |"),
    ("PROJECT-ROLES",
     "| 禁用管理员账号 | ❌ | ❌ | ❌（400，禁止） |\n\n# 4. 数据归属边界",
     "| 禁用管理员账号 | ❌ | ❌ | ❌（400，禁止） |\n\n> 当前没有资料修改接口（auth 模块仅 register/login/me/logout）；不要设计“修改个人信息”用例（复核 2026-11-11）。\n\n# 4. 数据归属边界"),
    ("RULE-ORDER-001",
     "- 金额使用浮点数计算，最终只对订单总金额做 2 位小数四舍五入；单项小计未单独四舍五入。",
     "- 金额使用浮点数计算：预览返回的 `total_amount`/`discount_amount` 未舍入；创建订单落库时三金额与 `OrderItem.subtotal` 均 round 到 2 位（orders.py#L128-L130、#L158）。"),
    ("RULE-ORDER-002",
     "- `address_id` 为空、为 0 或缺失：400 `请选择收货地址`（创建订单）。",
     "- 创建订单 `address_id=0`：400 `请选择收货地址`；\n- 创建订单 `address_id` 缺失、为 null 或类型非法：400 `VALIDATION_ERROR`（FastAPI 请求校验，main.py#L47-L52）。"),
    ("RULE-ORDER-002",
     "1. 不传 `address_id` 创建订单，预期 400。",
     "1. 不传/null `address_id` 创建订单：400 `VALIDATION_ERROR` 参数校验失败。"),
    ("RULE-ORDER-002",
     "2. 传 `address_id=0`，预期 400。",
     "2. 传 `address_id=0`：400 `请选择收货地址`。"),
    ("REQ-ORDER-001",
     "| 创建订单缺少 `address_id` 或为 0 | 400 `请选择收货地址` |",
     "| 创建订单 `address_id=0` | 400 `请选择收货地址` |\n| 创建订单缺少/null/类型非法 `address_id` | 400 `VALIDATION_ERROR` |"),
    ("REQ-ORDER-001",
     "- 创建订单**不清空购物车**；",
     "- 创建订单**不清空购物车**；\n- 立即购买=加购后跳转 `/cart`，不支持直接结算（Q-01 已确认）；因加购对同 SKU 累加，连续“立即购买”可能使结算数量翻倍，超过库存时返回 400 `库存不足，无法合并`（Q-03）。"),
    ("FLOW-ORDER-001",
     "| 9 | 用户 | 对已完成订单发表评价（跨模块） | `POST /api/reviews` 返回 201 | 订单状态不变 | 商品评价列表出现该评价 |\n\n# 5. 分支流程",
     "| 9 | 用户 | 对已完成订单发表评价（跨模块） | `POST /api/reviews` 返回 201 | 订单状态不变 | 商品评价列表出现该评价 |\n\n> **UI 交互说明（复核 2026-11-11）**：第 5、6 步由支付页一次点击连续触发两个请求（`create` + `success` 或 `create` + `fail`），中间没有独立选择界面；UI 用例不要把两步写成两次点击。\n\n# 5. 分支流程"),
    ("FLOW-ORDER-001",
     "| 未达门槛 | 预览/创建订单 | 409 `未达优惠券门槛` | 提示门槛 |",
     "| 未达门槛 | 预览/创建订单 | 409 `未达优惠券门槛（满X可用）` | 提示门槛 |"),
    ("FLOW-ORDER-001",
     "管理员同意后 `REFUNDED` 并恢复库存，拒绝后回 `PAID`。",
     "管理员同意后 `REFUNDED` 并恢复库存；拒绝后当前回 `PAID`（已确认应恢复退款前状态，Q-04，属缺陷待修复）。"),
    ("STATE-ORDER-001",
     "| `COMPLETED` | 已完成 | 用户确认收货 | 是 | 写入 `completed_at` |",
     "| `COMPLETED` | 已完成 | 用户确认收货 | 否 | 写入 `completed_at`；可因退款进入 `REFUNDING` |"),
    ("STATE-ORDER-001",
     "7. `CANCELLED`、`COMPLETED`、`REFUNDED` 为终态，没有出边。",
     "7. `CANCELLED`、`REFUNDED` 为终态，没有出边；`COMPLETED` 可因退款进入 `REFUNDING`，不是终态。"),
    ("STATE-ORDER-001",
     "8. `PENDING_SHIPMENT` 在数据字典中存在，但没有任何写入路径，不能作为当前有效状态使用。",
     "8. `PENDING_SHIPMENT` 在数据字典中存在，但没有任何写入路径，不能作为当前有效状态使用。\n\n## 已确认决策（2026-11-11）\n\n- **Q-02**：不引入库存预占；超卖为 Demo 已知限制，支付时库存不足仍成功并以 `max(stock-qty,0)` 截断。\n- **Q-04**：退款被拒应恢复退款前状态（`PAID/SHIPPED/COMPLETED`）；当前统一回 `PAID` 属缺陷，修复需增加 `pre_refund_status` 快照。\n- **Q-08**：`PENDING_SHIPMENT` 未启用，不纳入当前有效状态机。\n- **Q-12**：当前无订单超时自动取消。"),
    ("API-ORDER-003",
     "| `payment` | object/null | 支付单：`id`、`payment_no`、`method`、`amount`、`method_cn`、`status`、`status_cn`、`paid_at` |",
     "| `payment` | object（仅存在支付记录时出现，缺省而非 null） | 支付单：`id`、`payment_no`、`method`、`amount`、`method_cn`、`status`、`status_cn`、`paid_at` |"),
    ("API-ORDER-003",
     "| `shipment` | object/null | 物流单：`id`、`company`、`tracking_number`、`status`、`status_cn`、`shipped_at` |",
     "| `shipment` | object（仅存在物流单时出现，缺省而非 null） | 物流单：`id`、`company`、`tracking_number`、`status`、`status_cn`、`shipped_at` |"),
    ("API-ORDER-003",
     "| `refund` | object/null | 售后：`id`、`status`、`status_cn`、`amount`、`reason`、`reject_reason` |",
     "| `refund` | object（仅存在退款记录时出现，缺省而非 null） | 售后：`id`、`status`、`status_cn`、`amount`、`reason`、`reject_reason` |"),
    ("API-ORDER-003",
     "注意：`payment` 为单对象关系。若同一订单存在多条支付记录（支付失败后重试），返回哪一条不确定。",
     "注意：`payment` 为单对象关系。SQLAlchemy 2.0.36 实测在存在 FAILED+SUCCESS 两条记录时确定性返回第一条（通常为 FAILED）并抛 `SAWarning: Multiple rows returned with uselist=False`；属已知缺陷（Q-05）。"),
    ("TEST-ENV",
     "| `SEED_MEDIA_DIR` | `backend/../seed_media` | 当前未被业务代码引用 |",
     "| `SEED_MEDIA_DIR` | `backend/seed_media`（实际解析路径，目录不存在） | 无业务代码消费；按 Q-13 删除 |"),
    ("TEST-ENV",
     "- 若必须容器化，先补齐目录或删除 `COPY` 行（需项目负责人确认）。",
     "- 已确认（2026-11-11，Q-13）：删除 `Dockerfile#L11` COPY、`docker-compose.yml#L9` 挂载与 `SEED_MEDIA_DIR` 环境变量、`config.py#L15`；修复前容器环境不得作为正式测试环境。"),
    ("TEST-ENV",
     "无 `/health` 接口；可用 `GET /` 返回固定 JSON 作为存活检查。",
     "无 `/health` 接口；可用 `GET /` 返回固定 JSON 作为存活检查。Swagger `/docs` 无环境门控，所有环境均暴露（main.py#L11-L15）。"),
    ("AUTO-FRAMEWORK",
     "- 没有页面操作，纯 API 验证。\n\n# 2. 支持的客户端和协议",
     "- 没有页面操作，纯 API 验证。\n\n## 1.3 当前可执行性（2026-11-11 实测）\n\n- 当前种子库（播种于 2026-09-21）中券#1「新人满100减10」已自然过期，可领券仅剩 2 张；`e2e_test.py#L80` 的“可领券>=3”不成立，`#L81` 的 `next(...)` 无默认值会抛 `StopIteration`，脚本中止，后续约 100 行断言不会执行。\n- 脚本无论成功失败都以 0 退出，CI 无法感知失败；执行前需重建种子库或改为动态取券，并补 `sys.exit(1)`。\n\n# 2. 支持的客户端和协议"),
    ("EXP-ORDER-001",
     "**观察**：同一订单可有多条 `payments`（失败重试），但 `Order.payment` 是 `uselist=False`，详情只暴露一条，取哪条不确定。",
     "**观察**：同一订单可有多条 `payments`（失败重试），但 `Order.payment` 是 `uselist=False`。SQLAlchemy 2.0.36 实测：存在 FAILED+SUCCESS 两条记录时确定性返回第一条（通常为 FAILED）并抛 `SAWarning`，属确定性缺陷而非“不确定”。"),
    ("EXP-ORDER-001",
     "**关联**：`AUTO-LIMITATIONS`、`DATA-ORDER-001`。\n\n# 3. 对评审的影响",
     "**关联**：`AUTO-LIMITATIONS`、`DATA-ORDER-001`。\n\n## R-11 发货接受空物流信息\n\n**观察**：`ShipRequest.company`/`tracking_number` 是必填 `str`，但无 `min_length`，传空字符串可发货成功；前端 `AdminOrders.tsx#L38、L107-L108` 有必填校验，风险仅在 API 层。\n\n**证据**：`schemas.py#L177-L181`、`admin.py#L156-L178`。\n\n**影响**：直连 API 可产生无物流信息的“已发货”订单，物流查询/签收断言失去意义。\n\n**建议用例**：API 传 `company=\"\"` 或 `tracking_number=\"\"`，期望 400/422（当前实际 200，属已确认缺陷，Q-11）。\n\n**关联**：`RULE-ORDER-010`、`API-ORDER-006`、`CONFLICT-011`。\n\n# 3. 对评审的影响"),
    ("API-ORDER-006",
     "- 是否应拒绝空物流公司/空运单号？",
     "- 已确认（2026-11-11，Q-11）：后端应拒绝空物流公司/空运单号；当前未校验，属缺陷待修复。前端 `AdminOrders.tsx#L38、L107-L108` 已有必填校验，API 用例应期望 400/422。"),
    ("DATA-ORDER-001",
     "当前库共 18 张表；与交易域直接相关的为上述 10 张。",
     "当前库共 18 张表；与交易域直接相关的为上述 11 张（`products` 与 `product_skus` 分开计）。"),
    ("DATA-ORDER-001",
     "- `end_time` 在领券和用券时校验。",
     "- `end_time` 在领券和用券时校验；\n- 已确认（Q-06）：`total_quantity` 语义为**发放总量**；当前领券按 `used_quantity` 判断、领券不计数，属已确认待修复不一致（CONFLICT-006）。"),
    ("TEST-DATA",
     "当前没有测试数据管理 API，也没有软删除/归档接口。",
     "当前没有测试数据管理 API，也没有软删除/归档接口。\n\n> 注意（2026-11-11 实测）：当前种子库券#1 已过期，`e2e_test.py#L80-L81` 的“可领券>=3”与 `next(...)` 会失败（StopIteration）；执行前需重建数据库或动态取券。"),
]

for doc_id, old, new in TARGETS:
    p = doc_paths.get(doc_id)
    if not p:
        errors.append(f"missing doc {doc_id}"); continue
    text = open(p, encoding="utf-8").read()
    if old not in text:
        errors.append(f"target not found in {doc_id}: {old[:60]!r}"); continue
    text = text.replace(old, new, 1)
    open(p, "w", encoding="utf-8").write(text)

# 更新 front matter 并追加复核记录
counts = {"approved": 0, "in_review": 0}
for doc_id, p in doc_paths.items():
    row = by_id.get(doc_id)
    if not row:
        errors.append(f"no review row for {doc_id}"); continue
    text = open(p, encoding="utf-8").read()
    parts = text.split("---", 2)
    if len(parts) < 3:
        errors.append(f"bad front matter {doc_id}"); continue
    fm, body = parts[1], parts[2]
    status = "approved" if row.get("修改后状态") == "approved" else "in_review"
    reviewer = row.get("审核人") or ""
    fm = re.sub(r"^status:.*$", f"status: {status}", fm, count=1, flags=re.M)
    fm = re.sub(r"^reviewer:.*$", f'reviewer: "{reviewer}"', fm, count=1, flags=re.M)
    fm = re.sub(r"^reviewed_at:.*$", "reviewed_at: 2026-11-11", fm, count=1, flags=re.M)
    fm = re.sub(r"^updated_at:.*$", "updated_at: 2026-11-12", fm, count=1, flags=re.M)
    review_status = "approved_after_review" if status == "approved" else "changes_applied_pending_reapproval"
    if "review_status:" not in fm:
        fm = re.sub(r"^(chunk_strategy:.*)$",
                    rf"\1\nreview_status: {review_status}\nchange_reason: \"2026-11-12 人工复核回写（审核结论：{row.get('审核结论','')}）\"",
                    fm, count=1, flags=re.M)
    text = "---" + fm + "---" + body
    text = append_review_record(text, row, status)
    open(p, "w", encoding="utf-8").write(text)
    counts[status] += 1

print("front matter counts:", counts)
print("documents:", len(doc_paths))
print("errors:", len(errors))
for e in errors:
    print(" -", e)
