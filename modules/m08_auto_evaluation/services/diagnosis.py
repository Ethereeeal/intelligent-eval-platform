"""黑盒失败标记（BRD §9.3）。

待测智能体仅返回最终答案，未提供可与平台 Gold Evidence 对齐的检索轨迹。
因此平台不推断 D1–D8 根因：答错仅标为 E2E（端到端失败、原因不可定位），
仅可观测的调用异常标为 D9。
"""
from __future__ import annotations


def diagnose(sample: dict, result: dict, scores: dict) -> str | None:
    """返回 D9 或 E2E；通过及未评分样本返回 None。"""
    error = (result or {}).get("error")
    if error:
        return "D9"
    score = (scores or {}).get("score")
    if score is not None and score < 0.5:
        return "E2E"
    return None
