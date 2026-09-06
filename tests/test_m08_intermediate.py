import unittest
from unittest.mock import MagicMock, patch

from modules.m08_auto_evaluation.services.intermediate_metrics import (
    aggregate_intermediate,
    normalize_intermediate_config,
    score_intermediate,
)
from modules.m08_auto_evaluation.services.adapter import HttpAdapter


class M08IntermediateMetricTests(unittest.TestCase):
    def test_intermediate_config_is_optional_and_deduplicates_nodes(self):
        self.assertEqual(
            normalize_intermediate_config({"enabled": True, "nodes": ["intent", "intent"]}),
            {"enabled": True, "nodes": ["intent"]},
        )
        self.assertEqual(
            normalize_intermediate_config(None),
            {"enabled": False, "nodes": []},
        )

    def test_intent_only_evaluates_classification(self):
        result = score_intermediate(
            {"intent_id": "balance_query"},
            {"node_outputs": {"intent": {"label": "balance_query", "slots": {"extra": "ignored"}}}},
            ["intent"],
        )
        self.assertTrue(result["nodes"]["intent"]["correct"])
        self.assertNotIn("slot_f1", result["nodes"]["intent"])

    def test_rewrite_without_constraint_annotation_only_scores_semantics(self):
        with patch(
            "modules.m08_auto_evaluation.services.intermediate_metrics.score_answer",
            return_value={"score": 0.9},
        ):
            result = score_intermediate(
                {"rewrite_reference": "请查询余额"},
                {"node_outputs": {"rewrite": {"text": "请查询余额"}}},
                ["rewrite"],
            )
        rewrite = result["nodes"]["rewrite"]
        self.assertEqual(rewrite["semantic_similarity"], 0.9)
        self.assertIsNone(rewrite["constraint_f1"])

    def test_intent_aggregate_returns_accuracy_and_macro_f1(self):
        items = [
            {"status": "scored", "reference": "a", "predicted": "a", "correct": True},
            {"status": "scored", "reference": "b", "predicted": "a", "correct": False},
        ]
        summary = aggregate_intermediate(
            [{"scores": {"intermediate": {"nodes": {"intent": item}}}} for item in items],
            ["intent"],
        )
        self.assertEqual(summary["nodes"]["intent"]["accuracy"], 0.5)
        self.assertEqual(summary["nodes"]["intent"]["macro_f1"], 0.3333)

    def test_rag_without_retrieval_is_data_missing_not_zero(self):
        result = score_intermediate(
            {"question": "问题", "gold_answer": "标准答案"},
            {"answer": "实际答案", "retrieved": None},
            ["rag"],
        )
        self.assertEqual(result["nodes"]["rag"]["status"], "data_missing")
        self.assertIsNone(result["nodes"]["rag"]["metrics"]["context_recall"])

    def test_http_adapter_reads_external_retrieval_and_node_paths(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = (
            b'{"answer":"ok","retrieved":["context"],'
            b'"nodes":{"intent":{"label":"balance_query"}}}'
        )
        with patch(
            "modules.m08_auto_evaluation.services.adapter.urlopen",
            return_value=response,
        ):
            result = HttpAdapter({
                "url": "https://agent.example.invalid/run",
                "retrieved_path": "retrieved",
                "node_outputs_path": "nodes",
            }).run_single("问题")
        self.assertEqual(result["retrieved"], ["context"])
        self.assertEqual(result["node_outputs"]["intent"]["label"], "balance_query")


if __name__ == "__main__":
    unittest.main()
