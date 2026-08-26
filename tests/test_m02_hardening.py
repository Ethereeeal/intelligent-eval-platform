from __future__ import annotations

import unittest

from modules.m02_eiu_coverage.schemas import EiuUpdate
from modules.m02_eiu_coverage.services.eiu_quality import EiuQualityEvaluator
from modules.m02_eiu_coverage.services.llm_client import LLMClient


class M02HardeningTests(unittest.TestCase):
    def test_llm_json_accepts_object_wrappers(self) -> None:
        self.assertEqual(
            LLMClient._repair_json('{"items": [{"statement": "x"}]}'),
            [{"statement": "x"}],
        )
        self.assertEqual(
            LLMClient._repair_json('[{"statement": "x"}]'),
            [{"statement": "x"}],
        )

    def test_constraints_size_is_limited(self) -> None:
        with self.assertRaises(ValueError):
            EiuUpdate(constraints={"value": "x" * (16 * 1024)})

    def test_candidate_complexity_is_explainable(self) -> None:
        blocks = [
            {"block_id": 1, "block_text": "客户授信额度不得超过 100 万元。", "section_path": "授信", "block_type": "paragraph"},
            {"block_id": 2, "block_text": "申请人应当提供担保材料。", "section_path": "授信", "block_type": "paragraph"},
        ]
        item = EiuQualityEvaluator(blocks).annotate(
            {"statement": "客户授信额度不得超过 100 万元，申请人应当提供担保材料。", "is_questionable": True},
            blocks[0],
        )
        self.assertEqual(item["complexity_level"], "L2")
        self.assertEqual(item["complexity_score"], 3)
        self.assertEqual(item["complexity_factors"]["numeric_count"], 1)
        self.assertIn("reasons", item["complexity_factors"])
