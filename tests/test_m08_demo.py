import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi import HTTPException
from openpyxl import load_workbook

from modules.m08_auto_evaluation import api
from modules.m08_auto_evaluation.api import _build_evaluation_workbook
from modules.m08_auto_evaluation.schemas import AdapterTestRequest, ErrorBookUpdateRequest
from modules.m08_auto_evaluation.services import runner
from modules.m08_auto_evaluation.services.adapter import HttpAdapter, MockAdapter, OpenAiCompatibleAdapter
from modules.m08_auto_evaluation.services.diagnosis import diagnose
from modules.m08_auto_evaluation.services.metrics import aggregate
from modules.m08_auto_evaluation.services.optimization import build_optimization


class _MeasuredAdapter(OpenAiCompatibleAdapter):
    def __init__(self):
        pass

    def _chat(self, messages):
        return f"answer-{len(messages)}", 12, 7


class M08DemoTests(unittest.TestCase):
    def test_aggregate_handles_error_results_without_scores(self):
        summary = aggregate(
            [{
                "status": "error",
                "scores": {"score": None},
                "difficulty": "unknown",
                "dimension": "rule",
                "diagnosis": "D9",
            }]
        )
        self.assertEqual(summary["error_count"], 1)
        self.assertEqual(summary["scored"], 0)
        self.assertIsNone(summary["passed_rate"])
        self.assertEqual(summary["by_difficulty"]["unknown"]["passed"], 0)
        self.assertEqual(summary["by_dimension"]["rule"]["passed"], 0)

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
                "agent_observations": {"used_document_tool": True, "sources": ["manual.docx"]},
            }],
        )
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        report = workbook["原始评测报告"]
        self.assertEqual(report["B2"].value, "如何查询余额？")
        self.assertEqual(report["E2"].value, 0.9)
        self.assertEqual(report["N2"].value, '{"used_document_tool": true, "sources": ["manual.docx"]}')
        self.assertEqual(workbook["运行摘要"]["B3"].value, "#5")

    def test_http_adapter_keeps_answer_and_additional_response_fields(self):
        adapter = HttpAdapter({
            "url": "http://agent.example.test/v1/qa",
            "observation_paths": {"首个来源": "sources.0"},
        })
        payload = {
            "answer": "可用回答",
            "used_document_tool": True,
            "sources": ["manual.docx"],
            "request_id": "req-1",
        }
        self.assertEqual(adapter._resolve_path(payload, "answer"), "可用回答")
        self.assertEqual(
            adapter._observations(payload),
            {
                "used_document_tool": True,
                "sources": ["manual.docx"],
                "request_id": "req-1",
                "首个来源": "manual.docx",
            },
        )

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

    def test_running_run_must_be_cancelled_before_permanent_delete(self):
        with patch.object(api._db, "get_evaluation_run", return_value={"run_id": 7, "status": "running"}):
            with self.assertRaises(HTTPException) as raised:
                api.delete_evaluation_run(7, confirm=True)
        self.assertEqual(raised.exception.status_code, 409)

    def test_permanent_delete_requires_explicit_confirmation(self):
        with patch.object(api._db, "get_evaluation_run", return_value={"run_id": 7, "status": "done"}):
            with self.assertRaises(HTTPException) as raised:
                api.delete_evaluation_run(7, confirm=False)
        self.assertEqual(raised.exception.status_code, 400)

    def test_ignored_issue_requires_a_reason(self):
        payload = ErrorBookUpdateRequest(status="ignored", resolution_note=None)
        with self.assertRaises(HTTPException) as raised:
            api.update_error_book(1, payload)
        self.assertEqual(raised.exception.status_code, 400)

    def test_adapter_test_returns_a_single_observable_answer(self):
        result = api.test_adapter(
            AdapterTestRequest(adapter="mock", adapter_config={"reply": "通路正常"}, question="测试")
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["answer"], "通路正常")

    def test_sensitive_adapter_values_are_not_persisted(self):
        sanitized = api._sanitize_adapter_config({
            "api_key": "secret",
            "headers": {"Authorization": "Bearer secret"},
            "url": "https://example.invalid/agent",
        })
        self.assertNotIn("api_key", sanitized)
        self.assertEqual(sanitized["headers"], {"Authorization": "***"})

    def test_case_retry_requires_manual_processing_before_verified(self):
        source = {
            "result_id": 50, "run_id": 8, "case_uid": "case-50", "question": "q",
            "gold_answer": "正确答案", "status": "failed", "attempt_no": 1,
        }

        class _RetryDb:
            issue_status = "open"
            updates = []

            def list_evaluation_result_attempts(self, result_id):
                return [source]

            def save_evaluation_case_result(self, **kwargs):
                return 51

            def update_evaluation_case_result(self, result_id, **kwargs):
                return {"result_id": result_id, **kwargs}

            def get_error_book_item_for_result(self, *args, **kwargs):
                return {"item_id": 7, "status": self.issue_status, "regression": []}

            def update_error_book_item(self, item_id, **kwargs):
                self.updates.append(kwargs)
                return kwargs

        class _ImmediateThread:
            def __init__(self, *, target, daemon):
                self.target = target

            def start(self):
                self.target()

        database = _RetryDb()
        with patch.object(runner, "DatabaseService", return_value=database), patch.object(
            runner.threading, "Thread", _ImmediateThread
        ):
            runner.start_case_retry_async(
                run_id=8,
                source_result=source,
                adapter=MockAdapter({"reply": "正确答案"}),
                analysis_threshold=0.8,
            )
        self.assertNotIn("status", database.updates[-1])

        database = _RetryDb()
        database.issue_status = "processed"
        with patch.object(runner, "DatabaseService", return_value=database), patch.object(
            runner.threading, "Thread", _ImmediateThread
        ):
            runner.start_case_retry_async(
                run_id=8,
                source_result=source,
                adapter=MockAdapter({"reply": "正确答案"}),
                analysis_threshold=0.8,
            )
        self.assertEqual(database.updates[-1]["status"], "verified")


if __name__ == "__main__":
    unittest.main()
