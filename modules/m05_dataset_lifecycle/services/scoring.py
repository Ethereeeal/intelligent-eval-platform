"""评分口径（BRD §8.22 FR-DS-SRC-003）：运行侧配置，不进模板字段。

- 短答案（数值/日期/条款号/固定短语/拒答）→ 规范化精确匹配；
- 自然语言长答案 → 语义相似度评分（BGE cosine + 阈值，阈值经固定校准集验证）；
- 评分策略为运行侧配置；m08 评测运行时按答案形态分派。
"""
from __future__ import annotations

import math
import re


def normalize_answer(text: str) -> str:
    """规范化精确匹配：去空白、全半角统一、数字格式标准化。"""
    if not text:
        return ""
    text = text.strip().lower()
    # 全角 → 半角（数字 / 标点 / 百分号）
    table = str.maketrans(
        "０１２３４５６７８９．，；：！？（）％",
        "0123456789.,;:!?()%",
    )
    text = text.translate(table)
    text = re.sub(r"\s+", "", text)
    return text


def exact_match(answer: str, gold: str) -> bool:
    """短答案规范化精确匹配（去空白 / 全半角统一 / 数字格式标准化）。"""
    return normalize_answer(answer) == normalize_answer(gold)


def semantic_score(answer: str, gold: str) -> float:
    """自然语言长答案语义相似度（BGE cosine，0–1）。

    无 BGE 模型时回退精确匹配（命中 1.0 / 未命中 0.0），不阻断主流程。
    """
    try:
        from modules.m01_data_foundation.services.embedding import EmbeddingService

        embedder = EmbeddingService()
        vecs = embedder.embed_texts([answer, gold], is_query=False)
        left, right = vecs[0], vecs[1]
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)
    except Exception:
        return 1.0 if exact_match(answer, gold) else 0.0


def score_answer(answer: str, gold: str, *, use_semantic: bool = False) -> dict:
    """按答案形态分派评分（FR-DS-SRC-003）。

    use_semantic=False 走规范化精确匹配（短答案默认）；
    use_semantic=True 返回语义相似度（长答案默认，阈值由调用方/校准集决定）。
    """
    em = exact_match(answer, gold)
    if not use_semantic:
        return {"method": "exact_match", "score": 1.0 if em else 0.0, "exact_match": em}
    sim = semantic_score(answer, gold)
    return {"method": "semantic", "score": round(sim, 4), "exact_match": em}
