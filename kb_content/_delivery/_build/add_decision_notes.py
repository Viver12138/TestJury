import os
KB = r"C:\Users\Viver\Desktop\综合电商测试平台demo\kb_content\minishop"
notes = {
 "RULE-ORDER-003": "> 已确认（2026-11-11，Q-02）：不引入库存预占；超卖为 Demo 已知限制，支付时按 `max(stock-qty,0)` 截断，不再作为未决问题。",
 "RULE-ORDER-004": "> 已确认（2026-11-11，Q-06/Q-07）：`total_quantity` 为发放总量；未生效券不应可领用，当前不校验 `start_time` 属已知限制，需经 admin API 造数验证。",
 "RULE-ORDER-006": "> 已确认（2026-11-11，Q-03）：下单不清空购物车；立即购买=加购，同 SKU 累加，重复操作可能导致数量翻倍/超库存 400。",
 "RULE-ORDER-008": "> 已确认（2026-11-11，Q-05）：订单详情应展示成功/最新支付；当前 `Order.payment` 单对象关系为确定性缺陷（恒返回第一条 FAILED 并抛 SAWarning）。",
 "RULE-ORDER-009": "> 已确认（2026-11-11，Q-02）：不引入库存预占；超卖为已知限制，库存不足时支付仍成功并以 0 截断。",
 "RULE-ORDER-010": "> 已确认（2026-11-11，Q-04/Q-08/Q-11）：退款拒绝应恢复退款前状态；`PENDING_SHIPMENT` 未启用；后端应拒绝空物流信息。",
}
for doc_id, note in notes.items():
    p = os.path.join(KB, "rules", "order", doc_id + ".md")
    text = open(p, encoding="utf-8").read()
    marker = "\n\n---\n\n## 复核记录（人工复核，2026-11-11）"
    if marker not in text:
        print("marker missing", doc_id); continue
    if note in text:
        print("note exists", doc_id); continue
    text = text.replace(marker, "\n\n" + note + marker, 1)
    open(p, "w", encoding="utf-8").write(text)
    print("noted", doc_id)
