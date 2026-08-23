import unittest

from modules.m08_auto_evaluation.services.adapter import OpenAiCompatibleAdapter
from modules.m08_auto_evaluation.services.diagnosis import diagnose
from modules.m08_auto_evaluation.services.optimization import build_optimization


class _MeasuredAdapter(OpenAiCompatibleAdapter):
    def __init__(self):
        pass

    def _chat(self, messages):
        return f"answer-{len(messages)}", 12, 7


class M08DemoTests(unittest.TestCase):
    def test_multi_turn_usage_accumulates_model_calls(self):
        adapter = _MeasuredAdapter()
        result = adapter.run_multi(
            [
                {"q": "first", "key_turn": "memory"},
                {"q": "last"},
            ]
        )
        self.assertEqual(result["usage"], {"time_ms": 24, "tokens": 14, "cost": 0.0})

    def test_black_box_failure_is_not_assigned_a_retrieval_or_generation_cause(self):
        diagnosis = diagnose(
            {"gold_answer": "gold"},
            {"answer": "wrong", "retrieved": None},
            {"score": 0.0},
        )
        self.assertEqual(diagnosis, "E2E")
        self.assertIn("不对根因作进一步判断", build_optimization(diagnosis))

    def test_runtime_error_remains_d9(self):
        diagnosis = diagnose({}, {"error": "timeout"}, {"score": None})
        self.assertEqual(diagnosis, "D9")


if __name__ == "__main__":
    unittest.main()
