"""确定性规则评测。

规则评测只消费评测集已经提供的约束，不调用模型，也不自动从标准答案猜规则：

* ``must_have_points``：每个必答要点都必须出现在实际回答中；
* ``acceptable_answers``：实际回答规范化后，必须命中任一可接受完整答案。

字段为空时跳过对应检查。规则结果独立于现有的精确匹配/语义评分，避免改变
历史运行的最终答案评分口径。
"""
from __future__ import annotations

import json
from typing import Any

from modules.m05_dataset_lifecycle.services.scoring import normalize_answer


def _as_text_list(value: Any) -> list[str]:
    """兼容数据库 JSON 文本和已解析列表，过滤空值。"""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [
        text
        for item in value
        if item is not None
        for text in [str(item).strip()]
        if text
    ]


def evaluate_rules(sample: dict[str, Any], answer: str | None) -> dict[str, Any] | None:
    """根据评测集约束执行规则评测，无约束时返回 ``None``。"""
    must_have_points = _as_text_list(sample.get("must_have_points"))
    acceptable_answers = _as_text_list(sample.get("acceptable_answers"))
    if not must_have_points and not acceptable_answers:
        return None

    normalized_answer = normalize_answer(answer or "")
    point_checks = [
        {
            "point": point,
            "passed": normalize_answer(point) in normalized_answer,
        }
        for point in must_have_points
    ]
    missing_points = [item["point"] for item in point_checks if not item["passed"]]
    points_passed = not missing_points
    matched_point_count = len(point_checks) - len(missing_points)

    matched_answer_indexes = [
        index
        for index, candidate in enumerate(acceptable_answers)
        if normalized_answer == normalize_answer(candidate)
    ]
    acceptable_passed = not acceptable_answers or bool(matched_answer_indexes)
    passed = points_passed and acceptable_passed

    return {
        "method": "rules",
        "score": 1.0 if passed else 0.0,
        "passed": passed,
        "must_have_points": {
            "enabled": bool(must_have_points),
            "passed": points_passed if must_have_points else None,
            "checks": point_checks,
            "matched_count": matched_point_count,
            "total_count": len(point_checks),
            "recall": round(matched_point_count / len(point_checks), 4) if point_checks else None,
            "missing": missing_points,
        },
        "acceptable_answers": {
            "enabled": bool(acceptable_answers),
            "passed": acceptable_passed if acceptable_answers else None,
            "matched_indexes": matched_answer_indexes,
            "candidate_count": len(acceptable_answers),
        },
    }


__all__ = ["evaluate_rules"]
