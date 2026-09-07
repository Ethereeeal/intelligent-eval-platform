import unittest
import json

from modules.m02_eiu_coverage.services.eiu_gate_policy import EiuGatePolicy


def _item(statement: str, *, quality_status: str = "verified", block_id: int = 1) -> dict:
    checks = {
        "fidelity": {"status": "pass", "reasons": []},
        "completeness": {"status": "pass", "reasons": []},
        "atomicity": {"status": "pass", "reasons": []},
    }
    if quality_status != "verified":
        checks["completeness"] = {"status": "warning", "reasons": ["存在依赖上下文的指代：上述"]}
    return {
        "eiu_id": block_id,
        "block_id": block_id,
        "statement": statement,
        "eiu_type": "prohibition",
        "quality_status": quality_status,
        "quality_score": 1.0 if quality_status == "verified" else 0.8333,
        "quality_checks": checks,
        "is_questionable": True,
    }


class _ImportanceLLM:
    use_offline = False

    def __init__(self, level: str) -> None:
        self.level = level

    def extract_json(self, _system: str, _user: str) -> list[dict]:
        return [{
            "candidate_id": 0,
            "importance_level": self.level,
            "reason": "根据全文目录和核心结论判定",
            "evaluation_profiles": ["developer_smoke", "test_full", "business"],
        }]


class _BatchImportanceLLM:
    use_offline = False

    def __init__(self) -> None:
        self.calls = 0

    def extract_json(self, _system: str, user: str) -> list[dict]:
        self.calls += 1
        payload = json.loads(user)
        return [{
            "candidate_id": row["candidate_id"],
            "importance_level": "P2",
            "reason": "批量全文判定",
            "evaluation_profiles": ["test_full"],
        } for row in payload["candidates"]]


class EiuGatePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = {"document_id": 1, "file_name": "授信规则", "purpose": "规范授信办理"}
        self.blocks = [{"block_id": 1, "section_path": "第一章", "block_text": "不得接受他行存单"}]

    def test_offline_rule_type_does_not_directly_become_p0(self) -> None:
        items, _findings = EiuGatePolicy().apply_document(
            document=self.document, items=[_item("不得接受他行开立的单位定期存单质押")], blocks=self.blocks
        )
        self.assertEqual(items[0]["content_priority"], "P1")
        self.assertEqual(items[0]["auto_disposition"], "green")

    def test_unresolved_p0_stays_yellow_and_is_not_auto_generated(self) -> None:
        items, findings = EiuGatePolicy(_ImportanceLLM("P0")).apply_document(
            document=self.document,
            items=[_item("上述材料必须有效", quality_status="needs_review")],
            blocks=self.blocks,
        )
        self.assertEqual(items[0]["auto_disposition"], "yellow")
        self.assertTrue(items[0]["is_questionable"])
        self.assertTrue(any(finding["code"] == "p0_unresolved" for finding in findings))

    def test_unresolved_p1_is_archived(self) -> None:
        items, _findings = EiuGatePolicy(_ImportanceLLM("P1")).apply_document(
            document=self.document,
            items=[_item("上述材料必须有效", quality_status="needs_review")],
            blocks=self.blocks,
        )
        self.assertEqual(items[0]["auto_disposition"], "red")
        self.assertFalse(items[0]["is_questionable"])

    def test_only_exact_duplicates_are_archived(self) -> None:
        first = _item("不得接受他行开立的单位定期存单质押", block_id=1)
        duplicate = _item("不得接受他行开立的单位定期存单质押", block_id=2)
        items, _findings = EiuGatePolicy().apply_document(
            document=self.document, items=[first, duplicate], blocks=self.blocks
        )
        self.assertEqual(sum(item["auto_disposition"] == "green" for item in items), 1)
        self.assertEqual(sum(item["auto_disposition"] == "red" for item in items), 1)
        self.assertEqual(items[0]["canonical_intent_key"], items[1]["canonical_intent_key"])

    def test_importance_is_batched_before_final_disposition(self) -> None:
        llm = _BatchImportanceLLM()
        candidates = [_item(f"规则 {index}", block_id=index + 1) for index in range(21)]

        classified = EiuGatePolicy(llm).classify_document(
            document=self.document,
            items=candidates,
            blocks=self.blocks,
        )

        self.assertEqual(llm.calls, 2)
        self.assertTrue(all(item["content_priority"] == "P2" for item in classified))
        self.assertTrue(all("auto_disposition" not in item for item in classified))
