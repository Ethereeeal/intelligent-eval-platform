"""ErrorBook 失败记录（BRD §9.4）。

黑盒评测只记录端到端失败或运行异常；平台不对智能体根因作伪精确归因，
也不执行智能体调优或修改评测集。
"""
from __future__ import annotations

from collections import Counter

_SUGGESTIONS: dict[str, str] = {
    "E2E": "端到端回答未通过：待测智能体未提供可比对的检索轨迹，平台不对根因作进一步判断",
    "D9": "系统运行异常：记录超时、限流或接口错误，供待测智能体维护方排查",
}


def build_optimization(diagnosis: str) -> str:
    return _SUGGESTIONS.get(diagnosis, "建议人工复核该失败样本")


def cluster_error_book(items: list[dict]) -> list[dict]:
    """按归因聚类：优先处理影响面大的根因（FR-OPT-003）。"""
    counter = Counter(item.get("diagnosis") for item in items if item.get("diagnosis"))
    return [
        {"diagnosis": code, "count": count, "optimization": _SUGGESTIONS.get(code, "")}
        for code, count in counter.most_common()
    ]
