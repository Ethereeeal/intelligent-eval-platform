"""m03 评测集生成：泛化/改写扩写服务（README §2.6 模式 B 泛化 + §4.1 FR-VAR-001/002）。

以种子问答对（用户上传的，或系统生成的规范问答对）为输入，
扩写/改写/关联出数量更多、表述更多样的相关问题对。
所有泛化结果共享同一 intent_id 与标准答案，不重复计入 EIU 覆盖率。
"""
from __future__ import annotations

import json
import re
from typing import Any

from modules.m03_generation.models import GeneratedCase
from modules.m03_generation.services.llm_service import LLMService
from modules.m03_generation.services.prompts import build_variation_prompt
from modules.shared.core.config import settings
from modules.shared.services.database import DatabaseService


class VariationService:
    def __init__(self) -> None:
        self.database = DatabaseService()
        self.llm = LLMService()

    def generate_variations(
        self,
        seed_case: dict[str, Any],
        *,
        count: int = 3,
        styles: list[str] | None = None,
    ) -> list[dict]:
        """基于种子题生成 count 个变体，全部共享种子题的 intent_id 与标准答案。"""
        if count <= 0:
            return []
        styles = styles or ["formal", "colloquial", "omitted_subject", "reordered"]

        prompt = build_variation_prompt(
            question=seed_case["question"],
            gold_answer=seed_case["gold_answer"],
            must_have_points=seed_case.get("must_have_points") or [],
            acceptable_answers=seed_case.get("acceptable_answers") or [],
            styles=styles,
        )
        response = self.llm.call(prompt, temperature=0.4, max_tokens=settings.llm_max_tokens)
        variants = self._parse_variants(response)

        saved: list[dict] = []
        for variant in variants[:count]:
            question = str(variant.get("question") or "").strip()
            if not question:
                continue
            # 质量控制（简化，FR-VAR-002）：丢弃与种子完全相同的表述
            if question == seed_case["question"]:
                continue
            case = GeneratedCase(
                intent_id=seed_case["intent_id"],  # 共享同一意图
                eiu_id=seed_case.get("eiu_id"),
                document_id=seed_case.get("document_id"),
                question=question,
                question_type=seed_case["question_type"],
                difficulty=seed_case["difficulty"],
                scope_type=seed_case["scope_type"],
                gold_answer=seed_case["gold_answer"],  # 共享同一标准答案
                must_have_points=seed_case.get("must_have_points") or [],
                acceptable_answers=seed_case.get("acceptable_answers") or [],
                evidence=seed_case.get("evidence") or [],
                content_priority=seed_case["content_priority"],
                review_status="candidate",
            )
            saved.append(self.database.save_generated_case(
                intent_id=case.intent_id,
                eiu_id=case.eiu_id,
                document_id=case.document_id,
                question=case.question,
                question_type=case.question_type,
                difficulty=case.difficulty,
                scope_type=case.scope_type,
                gold_answer=case.gold_answer,
                must_have_points=case.must_have_points,
                acceptable_answers=case.acceptable_answers,
                evidence=case.evidence,
                content_priority=case.content_priority,
                review_status=case.review_status,
            ))
        return saved

    @staticmethod
    def _parse_variants(response: str) -> list[dict[str, Any]]:
        """宽容解析变体数组：支持整体 JSON / 代码块围栏 / 提取 question 列表。"""
        text = response.strip()
        candidates = [text]
        fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
        if fence_match:
            candidates.append(fence_match.group(1).strip())
        for candidate in candidates:
            try:
                data = json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
            if isinstance(data, dict) and isinstance(data.get("variants"), list):
                return [d for d in data["variants"] if isinstance(d, dict)]
        raise ValueError(f"无法解析泛化结果 JSON: {response[:300]}")
