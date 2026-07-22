from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
import math
import re


@dataclass
class RetrievalHit:
    block_id: int
    score: float
    source_excerpt: str
    document_id: int
    section_path: str | None


class RetrievalService:
    def score(self, question: str, blocks: list[dict]) -> list[RetrievalHit]:
        question_tokens = self._tokenize(question)
        hits: list[RetrievalHit] = []
        for block in blocks:
            block_tokens = self._tokenize(block["block_text"])
            overlap = len(set(question_tokens) & set(block_tokens))
            score = self._cosine_like(question_tokens, block_tokens) + overlap * 0.1
            hits.append(
                RetrievalHit(
                    block_id=block["block_id"],
                    score=round(score, 4),
                    source_excerpt=block["block_text"][:200],
                    document_id=block["document_id"],
                    section_path=block.get("section_path"),
                )
            )
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits

    def _tokenize(self, text: str) -> list[str]:
        return [token.lower() for token in re.findall(r"[\w\u4e00-\u9fff]+", text)]

    def _cosine_like(self, left_tokens: list[str], right_tokens: list[str]) -> float:
        if not left_tokens or not right_tokens:
            return 0.0
        left = Counter(left_tokens)
        right = Counter(right_tokens)
        common = set(left) & set(right)
        numerator = sum(left[token] * right[token] for token in common)
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)
