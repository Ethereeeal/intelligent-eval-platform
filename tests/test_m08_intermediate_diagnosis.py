import unittest
from unittest.mock import patch

from modules.m08_auto_evaluation.services.intermediate_diagnosis import (
    aggregate_intermediate_diagnosis,
    diagnose_intermediate,
    explain_intermediate,
)
from modules.m08_auto_evaluation.services.intermediate_metrics import aggregate_intermediate
from modules.m08_auto_evaluation.services import intermediate_diagnosis


class M08IntermediateDiagnosisTests(unittest.TestCase):
    def test_rule_diagnosis_covers_low_rewrite_intent_and_rag(self):
        diagnosis = diagnose_intermediate(
            {
                "nodes": {
                    "rewrite": {
                        "status": "scored",
                        "semantic_similarity": 0.4,
                        "constraint_precision": 0.5,
                        "constraint_recall": 0.6,
                        "constraint_f1": 0.54,
                        "full_constraint_preservation": False,
                    },
                    "intent": {
                        "status": "scored",
                        "reference": "balance_query",
                        "predicted": "transfer_query",
                        "correct": False,
                    },
                    "rag": {
                        "status": "scored",
                        "metrics": {
                            "context_precision": 0.4,
                            "context_recall": 0.8,
                            "faithfulness": 0.3,
                            "answer_relevancy": 0.6,
                        },
                    },
                }
            }
        )
        codes = {item["code"] for item in diagnosis["issues"]}
        self.assertEqual(diagnosis["status"], "issues_found")
        self.assertIn("rewrite.semantic_similarity_low", codes)
        self.assertIn("rewrite.constraint_not_preserved", codes)
        self.assertIn("intent.classification_mismatch", codes)
        self.assertIn("rag.context_precision_low", codes)
        self.assertIn("rag.faithfulness_low", codes)

    def test_missing_node_is_not_treated_as_zero_and_does_not_call_llm(self):
        intermediate = {
            "enabled": True,
            "nodes": {"rag": {"status": "data_missing", "metrics": {"context_recall": None}}},
        }
        with patch("modules.m08_auto_evaluation.services.intermediate_diagnosis.call") as mocked_call:
            result = explain_intermediate({"question": "问题"}, {"answer": "回答"}, intermediate)
        self.assertEqual(result["status"], "data_missing")
        self.assertEqual(result["explanation"]["status"], "data_missing")
        self.assertIsNone(intermediate["nodes"]["rag"]["metrics"]["context_recall"])
        mocked_call.assert_not_called()

    def test_healthy_nodes_do_not_need_model_explanation(self):
        intermediate = {
            "enabled": True,
            "nodes": {
                "rewrite": {"status": "scored", "semantic_similarity": 0.95},
                "intent": {"status": "scored", "correct": True},
                "rag": {
                    "status": "scored",
                    "metrics": {name: 0.95 for name in ("context_precision", "context_recall", "faithfulness", "answer_relevancy")},
                },
            },
        }
        with patch("modules.m08_auto_evaluation.services.intermediate_diagnosis.call") as mocked_call:
            result = explain_intermediate({}, {}, intermediate)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["explanation"]["status"], "not_needed")
        mocked_call.assert_not_called()

    def test_llm_explanation_is_structured_and_keeps_rule_issues(self):
        intermediate = {"enabled": True, "nodes": {"rewrite": {"status": "scored", "semantic_similarity": 0.4}}}
        raw = '{"summary":"改写丢失了核心条件","recommendations":[{"node":"rewrite","priority":"high","action":"补充约束保持示例","rationale":"语义相似度低"}]}'
        with patch.object(intermediate_diagnosis.settings, "llm_api_base", "https://llm.example/v1"), patch.object(
            intermediate_diagnosis.settings, "llm_api_key", "valid-key"
        ), patch.object(intermediate_diagnosis.settings, "llm_max_tokens", 512):
            with patch("modules.m08_auto_evaluation.services.intermediate_diagnosis.call", return_value=raw) as mocked_call:
                result = explain_intermediate(
                    {"question": "把问题改写"},
                    {"answer": "回答", "node_outputs": {"rewrite": {"text": "错误改写"}}},
                    intermediate,
                )
        self.assertEqual(result["status"], "issues_found")
        self.assertEqual(result["explanation"]["status"], "generated")
        self.assertEqual(result["explanation"]["recommendations"][0]["node"], "rewrite")
        mocked_call.assert_called_once()

    def test_llm_unavailable_preserves_rule_diagnosis(self):
        intermediate = {"enabled": True, "nodes": {"intent": {"status": "scored", "correct": False}}}
        with patch("modules.m08_auto_evaluation.services.intermediate_diagnosis.call") as mocked_call:
            result = explain_intermediate({}, {}, intermediate)
        self.assertEqual(result["status"], "issues_found")
        self.assertEqual(result["explanation"]["status"], "unavailable")
        self.assertTrue(result["issues"])
        mocked_call.assert_not_called()

    def test_aggregate_collects_top_issues_and_recommendations(self):
        diagnosis = {
            "status": "issues_found",
            "issues": [{"node": "intent", "code": "intent.classification_mismatch", "message": "分类错误", "suggestion": "补充边界样本", "severity": "high"}],
            "explanation": {"status": "generated", "recommendations": [{"node": "intent", "priority": "high", "action": "补充边界样本", "rationale": "标签易混淆"}]},
        }
        summary = aggregate_intermediate_diagnosis([
            {"scores": {"intermediate": {"diagnosis": diagnosis}}},
            {"scores": {"intermediate": {"diagnosis": diagnosis}}},
        ])
        self.assertEqual(summary["affected_cases"], 2)
        self.assertEqual(summary["top_issues"][0]["count"], 2)
        self.assertEqual(summary["recommendations"][0]["count"], 2)
        self.assertEqual(summary["llm_generated_count"], 2)

    def test_intermediate_summary_keeps_diagnosis_section(self):
        summary = aggregate_intermediate(
            [{"scores": {"intermediate": {"nodes": {"intent": {"status": "data_missing"}, "diagnosis": {"status": "data_missing", "issues": []}}}}}],
            ["intent"],
        )
        self.assertIn("diagnosis", summary)
        self.assertEqual(summary["diagnosis"]["status"], "data_missing")


if __name__ == "__main__":
    unittest.main()
