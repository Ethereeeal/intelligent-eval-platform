import unittest

from modules.m03_generation.services.pipeline import _default_angles_for_eiu, _is_generation_ready
from modules.m03_generation.services.prompts import build_qa_prompt


class M03EiuGateReadinessTests(unittest.TestCase):
    def test_batch_generation_consumes_only_green_eiu(self) -> None:
        self.assertTrue(_is_generation_ready({"auto_disposition": "green", "is_questionable": True}))
        self.assertFalse(_is_generation_ready({"auto_disposition": "yellow", "is_questionable": True}))
        self.assertFalse(_is_generation_ready({"auto_disposition": "red", "is_questionable": False}))

    def test_manual_override_requires_explicit_single_case_path(self) -> None:
        yellow = {"auto_disposition": "yellow", "is_questionable": True, "manual_include": True}
        self.assertFalse(_is_generation_ready(yellow))
        self.assertTrue(_is_generation_ready(yellow, allow_manual_override=True))

    def test_atomicity_warning_adds_multiple_single_fact_angles(self) -> None:
        eiu = {
            "quality_checks": {"atomicity": {"status": "warning", "reasons": ["多个谓词"]}},
            "complexity_factors": {"predicate_count": 3},
        }
        self.assertEqual(
            _default_angles_for_eiu(eiu),
            ["primary", "condition", "exception"],
        )

    def test_qa_prompt_explains_atomicity_without_making_it_a_gate(self) -> None:
        prompt = build_qa_prompt(
            statement="仅接受我行存单且资金必须为自有资金",
            eiu_type="rule",
            question_type="rule",
            angle="condition",
            context=[],
            block_text="仅接受我行存单且资金必须为自有资金。",
            section_path="业务要求",
            page_no=None,
            constraints=None,
            quality_checks={"atomicity": {"status": "warning", "reasons": ["检测到 2 个规范谓词"]}},
        )
        self.assertIn("原子性出题提示", prompt)
        self.assertIn("只覆盖其中一个事实", prompt)
