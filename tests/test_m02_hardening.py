from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from modules.m01_data_foundation.services.parser import DocumentParser
from modules.m02_eiu_coverage.schemas import EiuMergeRequest, EiuSplitRequest, EiuUpdate
from modules.m02_eiu_coverage.services import eiu_extractor
from modules.m02_eiu_coverage.services.claim_audit import (
    analyse_claim_relationships,
    audit_document_claim_coverage,
)
from modules.m02_eiu_coverage.services.context_bundle import ContextBundleBuilder
from modules.m02_eiu_coverage.services.eiu_extractor import (
    EiuExtractorService,
    _dedup_semantic,
    deterministic_extract,
)
from modules.m02_eiu_coverage.services.eiu_quality import EiuQualityEvaluator
from modules.m02_eiu_coverage.services.llm_client import LLMClient, LLMError


class M02HardeningTests(unittest.TestCase):
    def test_semantic_duplicate_stays_available_for_evidence_merge_review(self) -> None:
        items = _dedup_semantic(
            [{"statement": "\u7533\u8bf7\u4eba\u5e94\u5f53\u63d0\u4f9b\u5b58\u5355\u539f\u4ef6", "is_questionable": True}],
            [("\u7533\u8bf7\u4eba\u5e94\u5f53\u63d0\u4f9b\u5b58\u5355\u539f\u4ef6", [])],
        )
        self.assertTrue(items[0]["is_questionable"])
        self.assertTrue(items[0]["force_needs_review"])
        self.assertEqual(items[0]["review_action"], "merge")

    def test_document_audit_classifies_claim_relations_and_missing_coverage(self) -> None:
        eius = [
            {"eiu_id": 1, "document_id": 1, "block_id": 2, "statement": "\u7533\u8bf7\u4eba\u5e94\u5f53\u63d0\u4f9b\u5b58\u5355\u539f\u4ef6", "subject": "\u7533\u8bf7\u4eba", "predicate": "\u63d0\u4f9b", "modality": "\u5e94\u5f53", "is_questionable": True},
            {"eiu_id": 2, "document_id": 1, "block_id": 2, "statement": "\u7533\u8bf7\u4eba\u5e94\u5f53\u63d0\u4f9b\u5b58\u5355\u539f\u4ef6", "subject": "\u7533\u8bf7\u4eba", "predicate": "\u63d0\u4f9b", "modality": "\u5e94\u5f53", "is_questionable": False},
            {"eiu_id": 3, "document_id": 1, "block_id": 2, "statement": "\u7533\u8bf7\u4eba\u5e94\u5f53\u63d0\u4f9b\u5b58\u5355\u539f\u4ef6\u53ca\u81ea\u6709\u8d44\u91d1\u8bc1\u660e", "subject": "\u7533\u8bf7\u4eba", "predicate": "\u63d0\u4f9b", "modality": "\u5e94\u5f53", "is_questionable": True},
            {"eiu_id": 4, "document_id": 1, "block_id": 2, "statement": "\u7533\u8bf7\u4eba\u53ef\u4ee5\u63a5\u53d7\u5b58\u5355\u8d28\u62bc", "subject": "\u7533\u8bf7\u4eba", "predicate": "\u63a5\u53d7", "object": "\u5b58\u5355\u8d28\u62bc", "modality": "\u53ef\u4ee5", "is_questionable": True},
            {"eiu_id": 5, "document_id": 1, "block_id": 2, "statement": "\u7533\u8bf7\u4eba\u4e0d\u5f97\u63a5\u53d7\u5b58\u5355\u8d28\u62bc", "subject": "\u7533\u8bf7\u4eba", "predicate": "\u63a5\u53d7", "object": "\u5b58\u5355\u8d28\u62bc", "modality": "\u4e0d\u5f97", "is_questionable": True},
            {"eiu_id": 6, "document_id": 1, "block_id": 2, "statement": "\u7533\u8bf7\u4eba\u5e94\u5f53\u5728\u6388\u4fe1\u524d\u63d0\u4f9b\u5b58\u5355\u539f\u4ef6", "subject": "\u7533\u8bf7\u4eba", "predicate": "\u63d0\u4f9b", "modality": "\u5e94\u5f53", "is_questionable": True},
            {"eiu_id": 7, "document_id": 1, "block_id": 2, "statement": "\u7533\u8bf7\u4eba\u5e94\u5f53\u5728\u6388\u4fe1\u540e\u63d0\u4f9b\u5b58\u5355\u539f\u4ef6", "subject": "\u7533\u8bf7\u4eba", "predicate": "\u63d0\u4f9b", "modality": "\u5e94\u5f53", "is_questionable": True},
        ]
        relation_summary = analyse_claim_relationships(eius)
        self.assertGreaterEqual(relation_summary["exact_duplicate"], 1)
        self.assertGreaterEqual(relation_summary["contains"], 1)
        self.assertGreaterEqual(relation_summary["conflicts"], 1)
        self.assertGreaterEqual(relation_summary["overlaps"], 1)

        blocks = [
            {"block_id": 1, "document_id": 1, "block_type": "title", "block_text": "\u7b2c\u5341\u516b\u6761", "metadata_json": {"article_no": "\u7b2c\u5341\u516b\u6761"}},
            {"block_id": 2, "document_id": 1, "block_type": "paragraph", "block_text": "\u7532" * 320 + "\u6309\u7b2c\u5341\u4e5d\u6761\u6267\u884c", "metadata_json": {}},
            {"block_id": 3, "document_id": 1, "block_type": "paragraph", "block_text": "\u6682\u65e0\u77e5\u8bc6\u70b9", "metadata_json": {}},
        ]
        audit = audit_document_claim_coverage(blocks, eius[:1])[0]
        self.assertEqual(audit["blocks_without_claim_count"], 1)
        self.assertEqual(audit["long_single_claim_block_count"], 1)
        self.assertEqual(audit["unresolved_reference_block_count"], 1)

    def test_deterministic_candidate_has_structured_claim_fields(self) -> None:
        items = deterministic_extract("\u7533\u8bf7\u4eba\u4e0d\u5f97\u63a5\u53d7\u4ed6\u884c\u5f00\u7acb\u7684\u5b58\u5355\u8d28\u62bc\u3002")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["subject"], "\u7533\u8bf7\u4eba")
        self.assertEqual(items[0]["modality"], "\u4e0d\u5f97")
        self.assertEqual(items[0]["predicate"], "\u63a5\u53d7")
        self.assertIn("\u4ed6\u884c", items[0]["object"])

    def test_green_route_uses_quality_gate_not_surface_subject_presence(self) -> None:
        service = EiuExtractorService()
        service.llm.use_offline = True
        direct = {"block_id": 1, "block_text": "\u672c\u89c4\u7a0b\u81ea\u5370\u53d1\u4e4b\u65e5\u8d77\u65bd\u884c\u3002", "block_type": "paragraph", "section_path": "\u603b\u5219"}
        direct_items = service._extract_block(direct, {"file_name": "x.docx"}, {"prev": "", "next": ""})
        self.assertEqual(direct_items[0]["route_color"], "green")
        missing_subject = {"block_id": 2, "block_text": "\u5e94\u5f53\u63d0\u4f9b\u5b58\u5355\u539f\u4ef6\u3002", "block_type": "paragraph", "section_path": "\u603b\u5219"}
        pending_items = service._extract_block(missing_subject, {"file_name": "x.docx"}, {"prev": "", "next": ""})
        self.assertEqual(pending_items[0]["route_color"], "green")
        self.assertTrue(pending_items[0]["route_reasons"])

    def test_parser_preserves_article_and_list_lead_relationship(self) -> None:
        blocks = DocumentParser()._assign_hierarchy([
            {"text": "\u7b2c\u5341\u516b\u6761 \u5355\u4f4d\u5b9a\u671f\u5b58\u5355\u8d28\u62bc\u5e94\u5f53\u6ee1\u8db3\u4e0b\u5217\u6761\u4ef6\uff1a", "level": 3, "block_type": "title", "metadata": {"article_no": "\u7b2c\u5341\u516b\u6761"}},
            {"text": "\u7533\u8bf7\u4eba\u5e94\u63d0\u4f9b\u4e0b\u5217\u6750\u6599\uff1a", "level": None, "block_type": "paragraph"},
            {"text": "\uff08\u4e00\uff09\u5b58\u5355\u8d44\u91d1\u4e3a\u5b58\u6b3e\u4eba\u81ea\u6709\u8d44\u91d1\u3002", "level": None, "block_type": "list_item", "metadata": {"item_no": "\uff08\u4e00\uff09"}},
        ])
        self.assertEqual(blocks[2].parent_index, 1)
        self.assertEqual(blocks[2].metadata_json["article_no"], "\u7b2c\u5341\u516b\u6761")
        self.assertEqual(blocks[2].metadata_json["list_path"], "\u7b2c\u5341\u516b\u6761/\uff08\u4e00\uff09")

    def test_parser_does_not_merge_adjacent_list_or_table_rows(self) -> None:
        raw = [
            {"text": "\uff08\u4e00\uff09A", "level": None, "block_type": "list_item"},
            {"text": "\uff08\u4e8c\uff09B", "level": None, "block_type": "list_item"},
            {"text": "A | B", "level": None, "block_type": "table_row"},
            {"text": "C | D", "level": None, "block_type": "table_row"},
        ]
        self.assertEqual(len(DocumentParser()._merge_consecutive(raw)), 4)

    def test_context_bundle_collects_lead_article_reference_and_table_header(self) -> None:
        blocks = [
            {"block_id": 1, "block_text": "\u7b2c\u5341\u516b\u6761 \u7533\u8bf7\u4eba\u5e94\u63d0\u4f9b\u4e0b\u5217\u6750\u6599\uff1a", "block_type": "paragraph", "metadata_json": {"article_no": "\u7b2c\u5341\u516b\u6761"}},
            {"block_id": 2, "parent_block_id": 1, "block_text": "\uff08\u4e00\uff09\u5b58\u5355\u539f\u4ef6\u3002", "block_type": "list_item", "metadata_json": {"article_no": "\u7b2c\u5341\u516b\u6761", "item_no": "\uff08\u4e00\uff09"}},
            {"block_id": 3, "block_text": "\u7b2c\u4e8c\u5341\u6761 \u6309\u7b2c\u5341\u516b\u6761\u6267\u884c\u3002", "block_type": "paragraph", "metadata_json": {"article_no": "\u7b2c\u4e8c\u5341\u6761"}},
            {"block_id": 4, "block_text": "\u8d44\u6599\u540d\u79f0 | \u539f\u4ef6", "block_type": "table_header", "metadata_json": {"table_id": "t1"}},
            {"block_id": 5, "block_text": "\u5b58\u5355 | \u662f", "block_type": "table_row", "metadata_json": {"table_id": "t1"}},
        ]
        builder = ContextBundleBuilder(blocks)
        bundle = builder.build_all()
        self.assertEqual(bundle[2]["lead"], blocks[0]["block_text"])
        self.assertIn(blocks[0]["block_text"], bundle[3]["references"])
        self.assertEqual(bundle[5]["table_headers"], blocks[3]["block_text"])
        source_roles = {source["block_id"]: source["roles"] for source in bundle[2]["evidence_sources"]}
        self.assertIn("parent", source_roles[1])
        self.assertIn("lead", source_roles[1])
        expanded = builder.expand(bundle[2], [{"kind": "reference", "article_no": "\u7b2c\u4e8c\u5341\u6761"}])
        expanded_roles = {source["block_id"]: source["roles"] for source in expanded["evidence_sources"]}
        self.assertIn("requested_reference", expanded_roles[3])
        self.assertIn(blocks[2]["block_text"], expanded["expanded_context"])

    def test_yellow_review_can_request_graph_expansion_then_retry(self) -> None:
        service = EiuExtractorService()
        service.llm.use_offline = False
        service.llm.extract_json = Mock(side_effect=[
            [{"context_requests": [{"kind": "reference", "article_no": "\u7b2c\u5341\u516b\u6761"}]}],
            [{"statement": "\u7533\u8bf7\u4eba\u5e94\u5f53\u6309\u7b2c\u5341\u516b\u6761\u63d0\u4f9b\u6750\u6599", "review_action": "complete_context", "evidence_block_ids": [1, 2]}],
        ])
        blocks = [
            {"block_id": 1, "block_text": "\u4e0a\u8ff0\u6750\u6599\u5e94\u5f53\u6309\u7b2c\u5341\u516b\u6761\u8981\u6c42\u63d0\u4f9b\u3002", "block_type": "paragraph", "section_path": "\u6388\u4fe1", "metadata_json": {}},
            {"block_id": 2, "block_text": "\u7b2c\u5341\u516b\u6761 \u6750\u6599\u5e94\u5305\u62ec\u5b58\u5355\u539f\u4ef6\u3002", "block_type": "paragraph", "section_path": "\u6388\u4fe1", "metadata_json": {"article_no": "\u7b2c\u5341\u516b\u6761"}},
        ]
        context = ContextBundleBuilder(blocks).build_all()[1]
        items = service._extract_block(blocks[0], {"file_name": "x.docx"}, context)
        self.assertEqual(service.llm.extract_json.call_count, 2)
        self.assertEqual(items[0]["review_action"], "complete_context")
        self.assertEqual(items[0]["evidence_blocks"], [1, 2])

    def test_yellow_review_batches_same_article_and_reuses_tagged_results(self) -> None:
        service = EiuExtractorService()
        service.llm.use_offline = False
        service.llm.extract_json = Mock(return_value=[
            {
                "block_id": 1,
                "statement": "\u7533\u8bf7\u4eba\u5e94\u5f53\u63d0\u4f9b\u5b58\u5355\u539f\u4ef6",
                "review_action": "complete_context",
                "evidence_block_ids": [1],
            },
            {
                "block_id": 2,
                "statement": "\u7533\u8bf7\u4eba\u4e0d\u5f97\u63a5\u53d7\u4ed6\u884c\u5b58\u5355\u8d28\u62bc",
                "review_action": "complete_context",
                "evidence_block_ids": [2],
            },
        ])
        blocks = [
            {
                "block_id": 1,
                "block_text": "\u4e0a\u8ff0\u6750\u6599\u5e94\u5f53\u6309\u7b2c\u5341\u516b\u6761\u8981\u6c42\u63d0\u4f9b\u3002",
                "block_type": "paragraph",
                "section_path": "\u6388\u4fe1",
                "metadata_json": {"article_no": "\u7b2c\u5341\u516b\u6761"},
            },
            {
                "block_id": 2,
                "block_text": "\u4e0a\u8ff0\u6750\u6599\u4e0d\u5f97\u6309\u7b2c\u5341\u516b\u6761\u7528\u4e8e\u4ed6\u884c\u5b58\u5355\u8d28\u62bc\u3002",
                "block_type": "paragraph",
                "section_path": "\u6388\u4fe1",
                "metadata_json": {"article_no": "\u7b2c\u5341\u516b\u6761"},
            },
        ]
        contexts = ContextBundleBuilder(blocks).build_all()

        first_items = service._extract_block(blocks[0], {"file_name": "x.docx"}, contexts[1])
        second_items = service._extract_block(blocks[1], {"file_name": "x.docx"}, contexts[2])

        service.llm.extract_json.assert_called_once()
        self.assertIn("block_id=2", service.llm.extract_json.call_args.args[1])
        self.assertEqual(first_items[0]["evidence_blocks"], [1])
        self.assertEqual(second_items[0]["evidence_blocks"], [2])

    def test_inconsistent_context_retry_routes_result_to_manual_review(self) -> None:
        service = EiuExtractorService()
        service.llm.use_offline = False
        service.llm.extract_json = Mock(side_effect=[
            [
                {
                    "statement": "\u7533\u8bf7\u4eba\u5e94\u5f53\u6309\u7b2c\u5341\u516b\u6761\u63d0\u4f9b\u6750\u6599",
                    "review_action": "pass",
                    "evidence_block_ids": [1],
                },
                {"context_requests": [{"kind": "reference", "article_no": "\u7b2c\u5341\u516b\u6761"}]},
            ],
            [{
                "statement": "\u7533\u8bf7\u4eba\u5e94\u5f53\u6309\u7b2c\u5341\u516b\u6761\u63d0\u4f9b\u5b58\u5355\u539f\u4ef6",
                "review_action": "complete_context",
                "evidence_block_ids": [1, 2],
            }],
        ])
        blocks = [
            {"block_id": 1, "block_text": "\u4e0a\u8ff0\u6750\u6599\u5e94\u5f53\u6309\u7b2c\u5341\u516b\u6761\u8981\u6c42\u63d0\u4f9b\u3002", "block_type": "paragraph", "section_path": "\u6388\u4fe1", "metadata_json": {}},
            {"block_id": 2, "block_text": "\u7b2c\u5341\u516b\u6761 \u6750\u6599\u5e94\u5305\u62ec\u5b58\u5355\u539f\u4ef6\u3002", "block_type": "paragraph", "section_path": "\u6388\u4fe1", "metadata_json": {"article_no": "\u7b2c\u5341\u516b\u6761"}},
        ]
        items = service._extract_block(
            blocks[0], {"file_name": "x.docx"}, ContextBundleBuilder(blocks).build_all()[1]
        )

        self.assertEqual(items[0]["route_color"], "red")
        self.assertEqual(items[0]["review_action"], "human_review")
        self.assertIn("\u4e0d\u4e00\u81f4", "".join(items[0]["route_reasons"]))

    def test_llm_json_accepts_object_wrappers(self) -> None:
        self.assertEqual(
            LLMClient._repair_json('{"items": [{"statement": "x"}]}'),
            [{"statement": "x"}],
        )
        self.assertEqual(
            LLMClient._repair_json('[{"statement": "x"}]'),
            [{"statement": "x"}],
        )

    def test_llm_retries_only_once_for_transient_failure(self) -> None:
        service = LLMClient()
        service.use_offline = False
        service.max_attempts = 2
        response = Mock()
        response.choices = [Mock(message=Mock(content='{"items": []}'))]
        create = Mock(side_effect=[TimeoutError("slow upstream"), response])
        service._client = Mock(chat=Mock(completions=Mock(create=create)))

        with patch("modules.m02_eiu_coverage.services.llm_client.time.sleep") as sleep, self.assertLogs(
            "modules.m02_eiu_coverage.services.llm_client", level="INFO"
        ) as logs:
            result = service.chat([{"role": "user", "content": "x"}])

        self.assertEqual(result, '{"items": []}')
        self.assertEqual(create.call_count, 2)
        sleep.assert_called_once_with(1)
        self.assertIn("error_type=TimeoutError", logs.output[0])
        self.assertIn("will_retry=True", logs.output[0])
        self.assertIn("attempt_ms=", logs.output[0])
        self.assertNotIn("slow upstream", " ".join(logs.output))

    def test_review_circuit_breaker_stops_waiting_and_never_turns_green(self) -> None:
        service = EiuExtractorService()
        service.llm.use_offline = False
        service.llm.extract_json = Mock(side_effect=LLMError("timeout"))
        results = []
        for block_id in range(1, 5):
            block = {
                "block_id": block_id,
                "block_type": "paragraph",
                "block_text": "上述材料应当真实有效。",
                "section_path": "授信",
            }
            results.extend(service._extract_block(
                block,
                {"document_id": 1, "file_name": "授信规则.docx"},
                {"prev": "", "next": ""},
            ))

        self.assertEqual(service.llm.extract_json.call_count, 3)
        self.assertTrue(service._review_circuit_open)
        self.assertTrue(all(item["route_color"] != "green" for item in results))
        self.assertIn("停止继续等待", "".join(results[-1]["route_reasons"]))

    def test_constraints_size_is_limited(self) -> None:
        with self.assertRaises(ValueError):
            EiuUpdate(constraints={"value": "x" * (16 * 1024)})

    def test_manual_merge_and_split_contracts_require_multiple_distinct_items(self) -> None:
        self.assertEqual(EiuMergeRequest(source_eiu_ids=[1, 2], statement="\u5408\u5e76\u540e\u77e5\u8bc6\u70b9").source_eiu_ids, [1, 2])
        self.assertEqual(EiuSplitRequest(statements=["\u77e5\u8bc6\u70b9 A", "\u77e5\u8bc6\u70b9 B"]).statements[1], "\u77e5\u8bc6\u70b9 B")
        with self.assertRaises(ValueError):
            EiuSplitRequest(statements=["\u91cd\u590d", "\u91cd\u590d"])

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

    def test_forced_review_marker_does_not_override_two_hard_gates(self) -> None:
        block = {
            "block_id": 1,
            "block_text": "申请人应当提供存单原件。",
            "section_path": "授信",
            "block_type": "paragraph",
        }
        item = EiuQualityEvaluator([block]).annotate(
            {
                "statement": "申请人应当提供存单原件",
                "is_questionable": True,
                "force_needs_review": True,
            },
            block,
        )

        self.assertEqual(item["quality_status"], "verified")
        self.assertEqual(item["quality_checks"]["completeness"]["status"], "pass")

    def test_independent_rule_candidates_do_not_require_llm_consolidation(self) -> None:
        service = EiuExtractorService()
        service.llm.use_offline = False
        service.llm.extract_json = Mock(return_value=[
            {
                "statement": "仅接受我行开具的单位定期存单质押，不接受他行开立的单位定期存单质押",
                "is_questionable": True,
                "review_action": "merge",
                "source_candidate_indexes": [1, 2],
                "evidence_block_ids": [1],
            }
        ])
        block = {
            "block_id": 1,
            "block_type": "paragraph",
            "block_text": "仅接受我行开具的单位定期存单质押；不接受他行开立的单位定期存单质押。",
            "section_path": "质押授信",
        }

        items = service._extract_block(block, {"file_name": "质押授信.docx"}, {"prev": "", "next": ""})

        service.llm.extract_json.assert_not_called()
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item["extraction_model"] == "hybrid-rule" for item in items))
        self.assertTrue(all(item["route_color"] == "green" for item in items))

    def test_model_item_without_block_id_is_bound_to_current_block(self) -> None:
        service = EiuExtractorService()
        service.llm.use_offline = False
        service.llm.extract_json = Mock(return_value=[
            {
                "statement": "申请人应当按第十八条提供材料",
                "review_action": "complete_context",
                "evidence_block_ids": [1],
            }
        ])
        blocks = [
            {
                "block_id": 1,
                "document_id": 1,
                "block_type": "paragraph",
                "block_text": "第十八条 上述材料应当按第十八条要求提供。",
                "section_path": "授信",
                "metadata_json": {"article_no": "第十八条"},
            },
            {
                "block_id": 2,
                "document_id": 1,
                "block_type": "paragraph",
                "block_text": "第十八条 材料应包括存单原件。",
                "section_path": "授信",
                "metadata_json": {"article_no": "第十八条"},
            },
        ]

        items = service._extract_block(
            blocks[0], {"file_name": "x.docx"}, ContextBundleBuilder(blocks).build_all()[1]
        )

        self.assertEqual(items[0]["block_id"], 1)
        self.assertEqual(items[0]["evidence_blocks"], [1])

    def test_semantic_only_candidate_does_not_map_rule_type_to_p0(self) -> None:
        service = EiuExtractorService()
        service.llm.use_offline = False
        service.llm.extract_json = Mock(return_value=[{
            "statement": "申请人不得使用信贷资金开立质押存单",
            "review_action": "pass",
            "evidence_block_ids": [1],
        }])
        block = {
            "block_id": 1,
            "block_type": "paragraph",
            "block_text": "本段说明质押存单的资金来源边界。",
            "section_path": "质押授信",
        }

        items = service._extract_block(
            block,
            {"file_name": "授信规则.docx"},
            {"prev": "", "next": ""},
            rule_items_override=[],
        )

        self.assertEqual(items[0]["content_priority"], "P1")
        self.assertIn("不按规则类型升级", items[0]["importance_reason"])

    def test_unexpected_llm_review_error_falls_back_to_red_rule_candidate(self) -> None:
        service = EiuExtractorService()
        service.llm.use_offline = False
        service.llm.extract_json = Mock(side_effect=KeyError("block_id"))
        block = {
            "block_id": 1,
            "block_type": "paragraph",
            "block_text": "上述材料应当真实有效。",
            "section_path": "授信",
        }

        items = service._extract_block(block, {"file_name": "x.docx"}, {"prev": "", "next": ""})

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["route_color"], "red")
        self.assertEqual(items[0]["review_action"], "human_review")
        self.assertIn("KeyError", "".join(items[0]["route_reasons"]))

    def test_one_failed_block_does_not_abort_document_extraction(self) -> None:
        class FakeDatabase:
            def __init__(self) -> None:
                self.saved = []
                self.job_updates = []
                self.traces = []
                self.blocks = [
                    {
                        "block_id": 1,
                        "document_id": 1,
                        "block_type": "paragraph",
                        "block_text": "第一段内容。",
                        "section_path": "授信",
                        "metadata_json": {},
                    },
                    {
                        "block_id": 2,
                        "document_id": 1,
                        "block_type": "paragraph",
                        "block_text": "申请人应当提供担保材料。",
                        "section_path": "授信",
                        "metadata_json": {},
                    },
                ]

            def list_documents(self):
                return [{"document_id": 1, "file_name": "x.docx"}]

            def get_document_blocks(self, document_id):
                return self.blocks

            def delete_eius_by_document(self, *, document_id):
                return 0

            def update_job(self, job_id, **kwargs):
                self.job_updates.append((job_id, kwargs))

            def record_processing_trace(self, **kwargs):
                self.traces.append(kwargs)

            def save_eius(self, *, items):
                self.saved.extend(items)
                return list(range(1, len(items) + 1))

            def list_eius(self, *, document_id):
                return [
                    {
                        **item,
                        "eiu_id": index,
                        "document_id": document_id,
                        "quality_status": item.get("quality_status", "verified"),
                        "quality_checks": item.get("quality_checks") or {
                            "fidelity": {"status": "pass", "reasons": []},
                            "completeness": {"status": "pass", "reasons": []},
                            "atomicity": {"status": "pass", "reasons": []},
                        },
                    }
                    for index, item in enumerate(self.saved, start=1)
                ]

            def update_eiu(self, _eiu_id, **_updates):
                return None

            def replace_document_quality_findings(self, **_kwargs):
                return None

            def delete_generated_cases_by_document(self, *, document_id):
                return 0

        service = EiuExtractorService()
        service.database = FakeDatabase()
        service._extract_block = Mock(side_effect=[
            KeyError("block_id"),
            [{"statement": "申请人应当提供担保材料", "eiu_type": "rule", "is_questionable": True}],
        ])

        with patch.object(eiu_extractor, "_dedup_semantic", side_effect=lambda items, *_args: items), \
            patch.object(eiu_extractor, "_encode_one", return_value=None):
            result = service._run_locked(job_id=99, document_id=1)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["failed_blocks"], 1)
        self.assertEqual(len(service.database.saved), 2)
        self.assertEqual(service.database.saved[0]["extraction_model"], "eiu-extract-error")
        self.assertEqual(service.database.saved[0]["block_id"], 1)
        self.assertIn("失败 1 个 Block", service.database.job_updates[-1][1]["message"])
        self.assertTrue(any(trace["event"] == "block_excluded" for trace in service.database.traces))
        self.assertTrue(any(trace["event"] == "final_disposition" for trace in service.database.traces))
