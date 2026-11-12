from app.llm.base import ReviewOpinion
from app.pipeline.fusion import fuse


def test_same_step_and_category_does_not_merge_distinct_business_errors():
    base = {"scope": "step", "step_index": 1, "dimension": "business", "severity": "major",
            "category": "规则冲突", "evidence_status": "grounded"}
    price = {**base, "rationale": "客户端价格不能覆盖服务端金额", "evidence_quote": "金额0.01"}
    stock = {**base, "rationale": "数量超过库存应该拒绝", "evidence_quote": "库存1购买2成功"}
    opinions = [ReviewOpinion(role="chief_blind", summary="", issues=[price, stock]),
                ReviewOpinion(role="jury_a", summary="", issues=[price])]
    candidates = fuse("r", {}, opinions)
    assert len(candidates) == 2
    assert sorted(len(c.proposed_by) for c in candidates) == [1, 2]


def test_same_grounded_assertion_merges_paraphrases_but_not_another_correction():
    base = {"step_index": 1, "dimension": "business", "severity": "major", "category": "规则冲突",
            "evidence_quote": "响应金额和库存均为零", "kb_grounded": True, "kb_refs": ["pricing-rule"],
            "evidence_status": "grounded"}
    short = {**base, "rationale": "服务端金额按单价计算，不能为零", "suggestion": "预期改为 data.amount=45"}
    long = {**base, "rationale": "服务端金额按单价计算，不能为零。该数量乘以单价后应返回四十五元。",
            "suggestion": "检查 data.amount=45.00"}
    other = {**long, "suggestion": "检查 data.stock=7"}
    result = fuse("r", {}, [ReviewOpinion("chief_blind", "", [short]), ReviewOpinion("jury_a", "", [long])])
    assert len(result) == 1
    assert result[0].proposed_by == ["chief_blind", "jury_a"]
    assert len(fuse("r", {}, [ReviewOpinion("chief_blind", "", [short]),
                              ReviewOpinion("jury_a", "", [other])])) == 2


def test_identical_grounded_corrections_merge_even_with_different_explanations():
    base = {"step_index": 2, "dimension": "business", "severity": "major", "category": "规则冲突",
            "evidence_quote": "total=72; payable=1", "kb_grounded": True, "kb_refs": ["server-pricing"],
            "evidence_status": "grounded"}
    price = {**base, "rationale": "客户端传入的应付价格不参与计价，响应预期冲突",
             "suggestion": "改为 total=72, payable=72"}
    formula = {**base, "rationale": "无折扣时从购物项汇总并计算支付数值，断言应满足计算公式",
               "suggestion": "检查 payable=72.00; total=72"}
    opinions = [ReviewOpinion("chief_blind", "", [price]), ReviewOpinion("jury_b", "", [formula])]
    result = fuse("r", {}, opinions)
    assert len(result) == 1
    assert result[0].proposed_by == ["chief_blind", "jury_b"]
    # One shared assertion is not enough: these propose incompatible changes.
    conflict = {**formula, "suggestion": "检查 payable=71; total=72"}
    assert len(fuse("r", {}, [opinions[0], ReviewOpinion("jury_b", "", [conflict])])) == 2
    assert len(fuse("r", {}, [opinions[0], ReviewOpinion("jury_b", "", [{**conflict,
                                            "rationale": price["rationale"]}])])) == 2
    # Same correction without the same source or source quote is not proof of the same defect.
    for different in ({"kb_refs": ["different-rule"]}, {"evidence_quote": "another expectation"},
                      {"kb_grounded": False}):
        assert len(fuse("r", {}, [opinions[0], ReviewOpinion("jury_b", "", [{**formula, **different}])])) == 2
