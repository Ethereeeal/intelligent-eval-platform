import unittest

from modules.m02_eiu_coverage.services.eiu_quality import EiuQualityEvaluator


def _block(block_id: int, text: str, section: str) -> dict:
    return {
        "block_id": block_id,
        "document_id": 1,
        "parent_block_id": None,
        "block_type": "paragraph",
        "block_text": text,
        "section_path": section,
    }


class EiuQualityTests(unittest.TestCase):
    def test_simple_claim_is_verified(self) -> None:
        block = _block(1, "借款人必须按期归还贷款。", "第一章/第一条")
        result = EiuQualityEvaluator([block]).annotate(
            {"statement": "借款人必须按期归还贷款", "is_questionable": True}, block
        )

        self.assertEqual(result["quality_status"], "verified")
        self.assertEqual(result["evidence_blocks"], [1])
        self.assertTrue(
            all(item["status"] == "pass" for item in result["quality_checks"].values())
        )

    def test_explicit_cross_block_reference_builds_evidence_chain(self) -> None:
        article_18 = _block(18, "第十八条 借款人必须提交有效担保材料。", "第五章/第十八条")
        article_19 = _block(19, "第十九条 复核应当按照第十八条要求执行。", "第五章/第十九条")
        result = EiuQualityEvaluator([article_18, article_19]).annotate(
            {"statement": "复核应当按照第十八条要求执行", "is_questionable": True}, article_19
        )

        self.assertEqual(result["evidence_blocks"], [19, 18])
        self.assertEqual(result["evidence_details"][1]["role"], "reference")

    def test_context_dependent_claim_requires_review(self) -> None:
        previous = _block(1, "申请人必须提交身份证明。", "第二章/第一条")
        current = _block(2, "上述材料应当真实有效。", "第二章/第二条")
        result = EiuQualityEvaluator([previous, current]).annotate(
            {"statement": "上述材料应当真实有效", "is_questionable": True}, current
        )

        self.assertEqual(result["quality_status"], "needs_review")
        self.assertEqual(result["evidence_blocks"], [2, 1])
        self.assertEqual(result["quality_checks"]["completeness"]["status"], "warning")

    def test_exclusion_is_rejected(self) -> None:
        block = _block(1, "附件", "附件")
        result = EiuQualityEvaluator([block]).annotate(
            {"statement": "附件", "is_questionable": False}, block
        )

        self.assertEqual(result["quality_status"], "rejected")

    def test_document_title_with_year_requires_review(self) -> None:
        block = _block(1, "单位定期存单质押授信业务操作规程（2025年版）", "文档标题")
        result = EiuQualityEvaluator([block]).annotate(
            {"statement": block["block_text"], "is_questionable": True}, block
        )

        self.assertEqual(result["quality_status"], "needs_review")
        self.assertEqual(result["quality_checks"]["testability"]["status"], "warning")
