import unittest
import sys
import types

if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.exceptions = types.SimpleNamespace(RequestException=Exception)
    sys.modules["requests"] = requests_stub

from modules.m04_quality_governance.models import CheckItem, QualityReport
from modules.m04_quality_governance.schemas import HARD_CHECKS
from modules.m04_quality_governance.services.pipeline import PipelineService
from modules.m04_quality_governance.services.quality_checker import QualityChecker


class _PublishedCasePipeline(PipelineService):
    def __init__(self):
        self.updated = False

    def _check_and_persist(self, case):
        return QualityReport(
            case_id=case["case_id"],
            checks=[CheckItem("answerability", False, "无法由原文回答")],
        )

    def _regenerate_until_pass(self, case):
        raise AssertionError("published case must not regenerate")

    @property
    def database(self):
        return self

    @database.setter
    def database(self, value):
        pass

    def update_generated_case(self, *args, **kwargs):
        self.updated = True


class _DefaultBatchPipeline(PipelineService):
    def __init__(self):
        self.requested_statuses = []
        self.database = self

    def list_generated_cases(self, *, document_id, status):
        self.requested_statuses.append((document_id, status))
        return [{"case_id": 1, "review_status": status}]

    def _check_and_handle(self, case, *, preserve_status=False):
        return QualityReport(
            case_id=case["case_id"],
            checks=[CheckItem("answerability", True, "通过")],
        )


class M04HardeningTests(unittest.TestCase):
    def test_non_boolean_passed_value_fails_closed(self):
        checks = QualityChecker._normalize_checks(
            [{"check_type": "answerability", "passed": "false"}]
        )
        answerability = next(item for item in checks if item.check_type == "answerability")
        self.assertFalse(answerability.passed)
        self.assertIn("不是布尔值", answerability.reason)

    def test_answerability_is_a_hard_check(self):
        self.assertIn("answerability", HARD_CHECKS)

    def test_published_case_keeps_its_status_during_full_check(self):
        pipeline = _PublishedCasePipeline()
        report = pipeline._check_and_handle(
            {"case_id": 1, "review_status": "published"}, preserve_status=True
        )
        self.assertFalse(report.passed)
        self.assertFalse(pipeline.updated)

    def test_default_batch_only_checks_pending_statuses(self):
        pipeline = _DefaultBatchPipeline()
        summary = pipeline.run_quality_check(document_id=7)
        self.assertEqual(
            pipeline.requested_statuses,
            [(7, "candidate"), (7, "needs_review")],
        )
        self.assertEqual(summary["total_cases"], 2)
        self.assertEqual(summary["passed"], 2)


if __name__ == "__main__":
    unittest.main()
