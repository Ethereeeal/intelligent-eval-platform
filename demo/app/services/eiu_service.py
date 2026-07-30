from __future__ import annotations

from typing import Any

from app.services.database import DatabaseService
from app.services.llm_service import LLMService


class EiuService:
    def __init__(self) -> None:
        self.database = DatabaseService()
        self.llm = LLMService()

    def extract_eius(self, document_id: int) -> list[dict[str, Any]]:
        blocks = self.database.list_blocks_for_document(document_id)
        if not blocks:
            return []

        extracted = []
        for block in blocks:
            text = block["block_text"].strip()
            if not text:
                continue

            prompt = self._build_eiu_prompt(text)
            response = self.llm.call(prompt, temperature=0.0, max_tokens=512)
            parsed = self._parse_llm_response(response, fallback_text=text)
            eiu = self.database.save_eiu(
                document_id=document_id,
                corpus_id=block.get("corpus_id", 0),
                block_id=block["block_id"],
                statement=parsed["statement"],
                eiu_type=parsed["eiu_type"],
                content_priority=parsed["content_priority"],
                weight=parsed["weight"],
                constraints_json=parsed.get("constraints_json", {}),
                evidence_blocks=[block["block_id"]],
                is_questionable=parsed.get("is_questionable", True),
                exclusion_reason=parsed.get("exclusion_reason"),
                extraction_model=self.llm.model,
                extraction_confidence=parsed.get("extraction_confidence", 0.8),
            )
            extracted.append(eiu)
        return extracted

    def _build_eiu_prompt(self, text: str) -> str:
        return (
            "你是一个业务文档分析专家。请把下面的段落抽取为可评测信息单元（EIU）：\n"
            f"段落：{text}\n"
            "请返回 JSON，包含字段：statement、eiu_type、content_priority、weight、constraints_json、is_questionable、exclusion_reason。"
        )

    def _parse_llm_response(self, response: str, fallback_text: str) -> dict[str, Any]:
        try:
            import json

            data = json.loads(response)
            return {
                "statement": data.get("statement", fallback_text),
                "eiu_type": data.get("eiu_type", "rule"),
                "content_priority": data.get("content_priority", "P2"),
                "weight": data.get("weight", 1),
                "constraints_json": data.get("constraints_json", {}),
                "is_questionable": data.get("is_questionable", True),
                "exclusion_reason": data.get("exclusion_reason"),
                "extraction_confidence": data.get("extraction_confidence", 0.8),
            }
        except Exception:
            return {
                "statement": fallback_text,
                "eiu_type": "rule",
                "content_priority": "P2",
                "weight": 1,
                "constraints_json": {},
                "is_questionable": True,
                "exclusion_reason": None,
                "extraction_confidence": 0.8,
            }
