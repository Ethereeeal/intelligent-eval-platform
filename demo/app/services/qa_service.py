from __future__ import annotations

from typing import Any

from app.services.database import DatabaseService
from app.services.llm_service import LLMService


class QAService:
    def __init__(self) -> None:
        self.database = DatabaseService()
        self.llm = LLMService()

    def generate_cases_for_corpus(self, corpus_id: int) -> list[dict[str, Any]]:
        eius = self.database.list_eius(corpus_id=corpus_id)
        cases = []
        for eiu in eius:
            prompt = self._build_qa_prompt(eiu)
            response = self.llm.call(prompt, temperature=0.0, max_tokens=512)
            parsed = self._parse_llm_response(response, fallback_text=eiu["statement"])
            evidence = [
                {
                    "document_id": eiu["document_id"],
                    "block_id": eiu["evidence_blocks"][0] if eiu["evidence_blocks"] else None,
                    "text": parsed["gold_answer"],
                }
            ]
            case = self.database.save_eval_case(
                eiu_id=eiu["eiu_id"],
                intent_id=f"intent_{eiu['eiu_id']}",
                question=parsed["question"],
                question_type=parsed["question_type"],
                difficulty=parsed["difficulty"],
                scope_type="single_segment",
                gold_answer=parsed["gold_answer"],
                must_have_points=parsed["must_have_points"],
                acceptable_answers=parsed["acceptable_answers"],
                evidence=evidence,
                content_priority=eiu["content_priority"],
                review_status="candidate",
            )
            cases.append(case)
        return cases

    def _build_qa_prompt(self, eiu: dict[str, Any]) -> str:
        return (
            "你是一个评测题目编写专家。请基于下面的 EIU 生成一条规范题目、一个标准答案、必须命中要点、和可接受同义答案。\n"
            f"EIU: {eiu['statement']}\n"
            "返回 JSON，字段包含：question、question_type、difficulty、gold_answer、must_have_points、acceptable_answers。"
        )

    def _parse_llm_response(self, response: str, fallback_text: str) -> dict[str, Any]:
        try:
            import json

            data = json.loads(response)
            return {
                "question": data.get("question", ""),
                "question_type": data.get("question_type", "rule"),
                "difficulty": data.get("difficulty", "L2"),
                "gold_answer": data.get("gold_answer", fallback_text),
                "must_have_points": data.get("must_have_points", [fallback_text]),
                "acceptable_answers": data.get("acceptable_answers", [fallback_text]),
            }
        except Exception:
            return {
                "question": f"请基于以下内容生成问题：{fallback_text}",
                "question_type": "rule",
                "difficulty": "L2",
                "gold_answer": fallback_text,
                "must_have_points": [fallback_text],
                "acceptable_answers": [fallback_text],
            }
