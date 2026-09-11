import unittest
from unittest.mock import patch

from modules.m08_auto_evaluation.services import judge
from modules.m08_auto_evaluation.services.metrics import aggregate, score_case


class M08JudgeTests(unittest.TestCase):
    def test_normalize_judge_config_requires_prompt_when_enabled(self):
        with self.assertRaises(ValueError):
            judge.normalize_judge_config({"enabled": True, "prompt": "  "})
        self.assertEqual(
            judge.normalize_judge_config(None),
            {
                "enabled": False,
                "prompt": "",
                "include_history": False,
                "include_intermediate": False,
                "include_retrieved": False,
            },
        )

    def test_prompt_always_contains_fixed_data_and_only_selected_optional_data(self):
        config = judge.normalize_judge_config({"enabled": True, "prompt": "只判断答案是否正确"})
        prompt, missing = judge.build_judge_prompt(
            config,
            {"question": "问题", "gold_answer": "标准答案", "turns": [{"q": "历史"}]},
            {"answer": "实际答案", "turn_trace": [{"question": "历史"}], "retrieved": ["片段"]},
        )
        self.assertEqual(missing, [])
        self.assertIn('"question": "问题"', prompt)
        self.assertIn('"gold_answer": "标准答案"', prompt)
        self.assertIn('"actual_answer": "实际答案"', prompt)
        self.assertNotIn('"history"', prompt)
        self.assertNotIn('"retrieved"', prompt)

    def test_selected_optional_data_is_required_and_added_to_prompt(self):
        config = judge.normalize_judge_config({
            "enabled": True,
            "prompt": "检查完整性",
            "include_history": True,
            "include_intermediate": True,
            "include_retrieved": True,
        })
        prompt, missing = judge.build_judge_prompt(
            config,
            {"question": "问题", "gold_answer": "标准答案"},
            {"answer": "实际答案", "turn_trace": [{"question": "历史"}], "node_outputs": {"intent": {"label": "查询"}}, "retrieved": ["片段"]},
        )
        self.assertEqual(missing, [])
        self.assertIn('"history"', prompt)
        self.assertIn('"intermediate"', prompt)
        self.assertIn('"retrieved"', prompt)
        _, missing = judge.build_judge_prompt(
            config,
            {"question": "问题", "gold_answer": "标准答案"},
            {"answer": "实际答案"},
        )
        self.assertEqual(missing, ["history", "intermediate", "retrieved"])

    def test_evaluate_judge_parses_structured_result(self):
        config = {"enabled": True, "prompt": "判断答案是否正确"}
        with patch.object(judge.settings, "llm_api_key", "test-key"), patch.object(
            judge, "call", return_value='{"score": 0.8, "passed": true, "reason": "覆盖核心事实", "criteria": [{"name": "完整性", "score": 0.75, "passed": true, "reason": "完整"}]}'
        ) as call:
            result = judge.evaluate_judge(
                {"question": "问题", "gold_answer": "标准答案"},
                {"answer": "实际答案"},
                config,
            )
        self.assertEqual(result["status"], "scored")
        self.assertEqual(result["score"], 0.8)
        self.assertTrue(result["passed"])
        self.assertEqual(result["criteria"][0]["name"], "完整性")
        call.assert_called_once()

    def test_evaluate_judge_keeps_missing_and_model_errors_unscored(self):
        config = {"enabled": True, "prompt": "判断"}
        missing = judge.evaluate_judge(
            {"question": "问题", "gold_answer": "标准答案"},
            {"answer": "实际答案"},
            {**config, "include_retrieved": True},
        )
        self.assertEqual(missing["status"], "data_missing")
        self.assertIsNone(missing["score"])
        with patch.object(judge.settings, "llm_api_key", "test-key"), patch.object(
            judge, "call", return_value="not json"
        ):
            failed = judge.evaluate_judge(
                {"question": "问题", "gold_answer": "标准答案"},
                {"answer": "实际答案"},
                config,
            )
        self.assertEqual(failed["status"], "error")
        self.assertIsNone(failed["score"])

    def test_score_case_and_aggregate_keep_judge_separate(self):
        config = {"enabled": True, "prompt": "判断"}
        with patch.object(judge.settings, "llm_api_key", "test-key"), patch.object(
            judge, "call", return_value='{"score": 0.9, "passed": true, "reason": "正确"}'
        ):
            scores = score_case(
                {"question": "问题", "gold_answer": "标准答案"},
                {"answer": "错误答案", "usage": {}},
                config,
            )
        self.assertEqual(scores["score"], 0.0)
        self.assertEqual(scores["judge"]["score"], 0.9)
        summary = aggregate([{"status": "failed", "scores": scores}], judge_config=config)
        self.assertTrue(summary["judge_enabled"])
        self.assertEqual(summary["judge_scored"], 1)
        self.assertEqual(summary["judge_passed_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
