from __future__ import annotations

import unittest

from modules.m02_eiu_coverage.schemas import EiuMergeRequest, EiuSplitRequest, EiuUpdate
from modules.m02_eiu_coverage.services.eiu_quality import EiuQualityEvaluator
from modules.m02_eiu_coverage.services.llm_client import LLMClient
from modules.m02_eiu_coverage.services.eiu_extractor import EiuExtractorService, _dedup_semantic, deterministic_extract
from modules.m02_eiu_coverage.services.context_bundle import ContextBundleBuilder
from modules.m02_eiu_coverage.services.claim_audit import (
    analyse_claim_relationships,
    audit_document_claim_coverage,
)
from modules.m01_data_foundation.services.parser import DocumentParser
from unittest.mock import Mock


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

    def test_green_route_requires_subject_and_single_predicate(self) -> None:
        service = EiuExtractorService()
        service.llm.use_offline = True
        direct = {"block_id": 1, "block_text": "\u672c\u89c4\u7a0b\u81ea\u5370\u53d1\u4e4b\u65e5\u8d77\u65bd\u884c\u3002", "block_type": "paragraph", "section_path": "\u603b\u5219"}
        direct_items = service._extract_block(direct, {"file_name": "x.docx"}, {"prev": "", "next": ""})
        self.assertEqual(direct_items[0]["route_color"], "green")
        missing_subject = {"block_id": 2, "block_text": "\u5e94\u5f53\u63d0\u4f9b\u5b58\u5355\u539f\u4ef6\u3002", "block_type": "paragraph", "section_path": "\u603b\u5219"}
        pending_items = service._extract_block(missing_subject, {"file_name": "x.docx"}, {"prev": "", "next": ""})
        self.assertEqual(pending_items[0]["route_color"], "red")
        self.assertIn("\u663e\u5f0f\u4e3b\u4f53", "".join(pending_items[0]["route_reasons"]))

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
            {"block_id": 1, "block_text": "\u7533\u8bf7\u4eba\u5e94\u5f53\u6309\u7b2c\u5341\u516b\u6761\u63d0\u4f9b\u6750\u6599\u3002", "block_type": "paragraph", "section_path": "\u6388\u4fe1", "metadata_json": {}},
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
                "block_text": "\u7533\u8bf7\u4eba\u5e94\u5f53\u6309\u7b2c\u5341\u516b\u6761\u63d0\u4f9b\u5b58\u5355\u539f\u4ef6\u3002",
                "block_type": "paragraph",
                "section_path": "\u6388\u4fe1",
                "metadata_json": {"article_no": "\u7b2c\u5341\u516b\u6761"},
            },
            {
                "block_id": 2,
                "block_text": "\u7533\u8bf7\u4eba\u4e0d\u5f97\u6309\u7b2c\u5341\u516b\u6761\u63a5\u53d7\u4ed6\u884c\u5b58\u5355\u8d28\u62bc\u3002",
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
            {"block_id": 1, "block_text": "\u7533\u8bf7\u4eba\u5e94\u5f53\u6309\u7b2c\u5341\u516b\u6761\u63d0\u4f9b\u6750\u6599\u3002", "block_type": "paragraph", "section_path": "\u6388\u4fe1", "metadata_json": {}},
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

    def test_yellow_rule_candidates_are_sent_to_llm_for_consolidation(self) -> None:
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

        service.llm.extract_json.assert_called_once()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["extraction_model"], "hybrid-llm")
        self.assertEqual(items[0]["eiu_type"], "rule")
        self.assertEqual(items[0]["route_color"], "yellow")
        self.assertEqual(items[0]["review_action"], "merge")
        self.assertEqual(items[0]["evidence_blocks"], [1])
        self.assertEqual(len(items[0]["source_candidate_ids"]), 2)
        self.assertIn("检测到 2 个业务谓词，需判断拆分或合并", items[0]["route_reasons"])
