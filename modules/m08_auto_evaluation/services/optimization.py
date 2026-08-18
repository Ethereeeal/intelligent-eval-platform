"""优化建议与 ErrorBook（BRD §9.4 FR-OPT-001~003）。

- FR-OPT-001：按 D1–D9 给出可执行优化建议；
- FR-OPT-003：ErrorBook 聚类（按归因统计），供 m06 回流工作台消费。
"""
from __future__ import annotations

from collections import Counter

_SUGGESTIONS: dict[str, str] = {
    "D1": "文档解析失败：检查解析器版本 / OCR 质量，修复表格结构与版面定位后重抽",
    "D2": "知识表示失败：补充术语表 / 指标口径，检查 EIU 拆分与关系",
    "D3": "检索召回失败：优化切块 / 查询理解 / 召回策略，检查 EIU 向量索引",
    "D4": "排序 / 上下文失败：调优重排、邻居扩展、上下文预算",
    "D5": "答案生成失败：优化提示词 / 模型 / 引用约束，检查证据是否完整进入上下文",
    "D6": "评测样本缺陷：修订题目 / 金标准 / 证据后发布新版本（m05 编辑）",
    "D7": "原始材料不足：改为拒答 / 补充资料 / 移出评测集",
    "D8": "安全策略失败：检查脱敏与提示注入防护规则",
    "D9": "系统运行异常：检查超时 / 限流 / 接口错误，重试或调整适配器配置",
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
