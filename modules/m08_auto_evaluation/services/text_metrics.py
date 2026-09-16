"""参考文本指标：GB/T 45288.2—2025 附录 A 所列 BLEU 与 ROUGE-L 公式。"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any

BLEU_PARAMETERS = {
    "max_order": 4,
    "weights": "available n-gram orders equally weighted",
    "smoothing": "add-one (sentence-level zero-count smoothing)",
    "tokenization": "CJK character / non-CJK word; punctuation excluded",
    "reference_selection": "maximum BLEU across available references",
}
ROUGE_L_PARAMETERS = {
    "beta": 1.0,
    "tokenization": "CJK character / non-CJK word; punctuation excluded",
    "reference_selection": "maximum ROUGE-L F1 across available references",
    "max_lcs_cells_per_reference": 500_000,
}
MAX_ROUGE_L_CELLS = ROUGE_L_PARAMETERS["max_lcs_cells_per_reference"]


def tokenize_text(value: str) -> list[str]:
    """避免隐式依赖分词模型：中日韩文本按字、其他文字按词切分。"""
    return re.findall(r"[\u3400-\u9fff]|[^\W_]+(?:['’._-][^\W_]+)*", str(value or "").lower(), re.UNICODE)


def _as_reference_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return [raw]
        return _as_reference_list(parsed) if parsed != raw else [raw]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _as_reference_list(item)]
    if isinstance(value, dict):
        for key in ("text", "content", "answer", "value"):
            if value.get(key) is not None:
                return _as_reference_list(value[key])
        return []
    return [str(value).strip()] if str(value).strip() else []


def reference_texts(sample: dict) -> list[str]:
    values = _as_reference_list(sample.get("gold_answer"))
    values.extend(_as_reference_list(sample.get("acceptable_answers")))
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def _ngrams(tokens: list[str], order: int) -> Counter[tuple[str, ...]]:
    return Counter(tuple(tokens[index : index + order]) for index in range(max(0, len(tokens) - order + 1)))


def bleu_score(candidate: str, references: list[str], max_order: int = 4) -> float | None:
    """句级 BLEU，采用最近参考长度、裁剪 n-gram 精确率、长度惩罚和加一平滑。"""
    candidate_tokens = tokenize_text(candidate)
    reference_tokens = [tokens for text in references if (tokens := tokenize_text(text))]
    if not candidate_tokens or not reference_tokens:
        return None

    candidate_length = len(candidate_tokens)
    reference_length = min(
        (len(tokens) for tokens in reference_tokens),
        key=lambda length: (abs(length - candidate_length), length),
    )
    active_orders = min(max_order, candidate_length)
    precisions: list[float] = []
    for order in range(1, active_orders + 1):
        candidate_counts = _ngrams(candidate_tokens, order)
        max_reference_counts: Counter[tuple[str, ...]] = Counter()
        for tokens in reference_tokens:
            for gram, count in _ngrams(tokens, order).items():
                max_reference_counts[gram] = max(max_reference_counts[gram], count)
        clipped = sum(min(count, max_reference_counts[gram]) for gram, count in candidate_counts.items())
        total = sum(candidate_counts.values())
        precisions.append((clipped + 1) / (total + 1))

    brevity_penalty = 1.0 if candidate_length > reference_length else math.exp(
        1 - reference_length / candidate_length
    )
    score = brevity_penalty * math.exp(sum(math.log(value) for value in precisions) / len(precisions))
    return round(score, 4)


def _lcs_length(left: list[str], right: list[str]) -> int:
    previous = [0] * (len(right) + 1)
    for left_item in left:
        current = [0]
        for index, right_item in enumerate(right, start=1):
            current.append(previous[index - 1] + 1 if left_item == right_item else max(previous[index], current[-1]))
        previous = current
    return previous[-1]


def rouge_l_score(candidate: str, references: list[str]) -> dict[str, float] | None:
    candidate_tokens = tokenize_text(candidate)
    reference_tokens = [tokens for text in references if (tokens := tokenize_text(text))]
    if not candidate_tokens or not reference_tokens:
        return None

    if any(len(candidate_tokens) * len(tokens) > MAX_ROUGE_L_CELLS for tokens in reference_tokens):
        return None

    best: tuple[float, float, float] | None = None
    for tokens in reference_tokens:
        lcs = _lcs_length(candidate_tokens, tokens)
        precision = lcs / len(candidate_tokens)
        recall = lcs / len(tokens)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        value = (f1, precision, recall)
        if best is None or value > best:
            best = value
    assert best is not None
    f1, precision, recall = best
    return {"score": round(f1, 4), "precision": round(precision, 4), "recall": round(recall, 4)}


def score_reference_metric(method: str, sample: dict, answer: str | None) -> dict:
    references = reference_texts(sample)
    if (
        not str(answer or "").strip()
        or not references
        or not tokenize_text(answer or "")
        or not any(tokenize_text(reference) for reference in references)
    ):
        return {
            "method": method,
            "status": "data_missing",
            "score": None,
            "reason": "缺少实际回答或标准参考文本",
            "reference_count": len(references),
            "parameters": dict(BLEU_PARAMETERS if method == "bleu" else ROUGE_L_PARAMETERS),
        }
    if method == "bleu":
        score = max((bleu_score(answer, [reference]) or 0.0) for reference in references)
        return {
            "method": "bleu",
            "status": "scored",
            "score": score,
            "reference_count": len(references),
            "parameters": dict(BLEU_PARAMETERS),
        }
    score = rouge_l_score(answer, references)
    if score is None:
        too_long = bool(tokenize_text(answer)) and any(
            len(tokenize_text(answer)) * len(tokenize_text(reference)) > MAX_ROUGE_L_CELLS
            for reference in references
        )
        return {
            "method": "rouge_l",
            "status": "unavailable" if too_long else "data_missing",
            "score": None,
            "reason": "输入过长，超过 LCS 计算上限" if too_long else "参考文本无法分词",
            "reference_count": len(references),
            "parameters": dict(ROUGE_L_PARAMETERS),
        }
    return {
        "method": "rouge_l",
        "status": "scored",
        **score,
        "reference_count": len(references),
        "parameters": dict(ROUGE_L_PARAMETERS),
    }
