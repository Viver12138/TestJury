import os
ROOT = r"C:\Users\Viver\Desktop\综合电商测试平台demo\kb_content\minishop"
notes = {
 os.path.join(ROOT,"project","versions.md"): "> 复核补充（2026-11-11 实测）：当前库券#1「新人满100减10」已于 2026-10-21 自然过期但 `status` 仍为 ACTIVE；seed 幂等不刷新有效期，领券/用券用例执行前须重建库或改用券#2/#3，否则会误判为产品缺陷。",
 os.path.join(ROOT,"testing","project_test_standards.md"): "> 复核补充：1187.0 的金额基线依赖已过期的新人券；重建种子库后成立，否则机械键盘×3 使用券#2 应为 1097.0。",
 os.path.join(ROOT,"automation","locator_and_assertion.md"): "> 复核补充：金额样例 `abs(pay-1187.0)<0.01` 依赖已过期新人券；重建种子库后成立，否则用券#2 → 1097.0。",
 os.path.join(ROOT,"glossary","terms.md"): "> 复核补充：`total_quantity` 语义应为发放总量；当前 `coupons.py#L83` 按 `used_quantity` 判“已领完”，属已确认待修复不一致（Q-06）。",
 os.path.join(ROOT,"interfaces","order","API-ORDER-002.md"): "> 复核补充：`payment_method` 仅定义于请求 Schema，`create_order` 未使用；用例不得断言其落库（复核 2026-11-11）。",
}
marker = "\n\n---\n\n## 复核记录（人工复核，2026-11-11）"
for p, note in notes.items():
    text = open(p, encoding="utf-8").read()
    if marker not in text:
        print("marker missing", p); continue
    if note in text:
        print("exists", os.path.basename(p)); continue
    text = text.replace(marker, "\n\n" + note + marker, 1)
    open(p, "w", encoding="utf-8").write(text)
    print("noted", os.path.basename(p))
