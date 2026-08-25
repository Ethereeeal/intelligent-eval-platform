import unittest
from io import BytesIO

from openpyxl import load_workbook

from modules.m08_auto_evaluation.api import _build_evaluation_workbook
from modules.m08_auto_evaluation.services.adapter import OpenAiCompatibleAdapter
from modules.m08_auto_evaluation.services.diagnosis import diagnose
from modules.m08_auto_evaluation.services.optimization import build_optimization


class _MeasuredAdapter(OpenAiCompatibleAdapter):
    def __init__(self):
        pass

    def _chat(self, messages):
        return f"answer-{len(messages)}", 12, 7


class M08DemoTests(unittest.TestCase):
    def test_evaluation_report_export_contains_raw_rows(self):
        content = _build_evaluation_workbook(
            {
                "run_id": 12,
                "composition_id": 5,
                "name": "客服回归评测",
                "adapter": "http",
                "status": "done",
                "created_at": "2026-08-25T10:00:00",
            },
            [{
                "result_id": 1,
                "case_uid": "case-1",
                "question": "如何查询余额？",
                "gold_answer": "登录后查询",
                "answer": "请登录手机银行查询",
                "scores": {"score": 0.9, "latency_ms": 120},
                "status": "passed",
                "dimension": "准确性",
                "difficulty": "easy",
                "source": "uploaded",
                "diagnosis": None,
                "error_message": None,
            }],
        )
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        report = workbook["原始评测报告"]
        self.assertEqual(report["B2"].value, "如何查询余额？")
        self.assertEqual(report["E2"].value, 0.9)
        self.assertEqual(workbook["运行摘要"]["B3"].value, "#5")

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
