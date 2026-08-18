"""失败归因（BRD §9.3 FR-DIAG-001/002，Demo 基础版）。

按归因顺序判断：原始资料有答案 → 金标准正确 → 解析 → 召回 → 上下文 → 答案生成 → 安全/格式。
待测系统未返回检索轨迹时标记"不可诊断检索层"，不强行归因 D3/D4。
"""
from __future__ import annotations


def diagnose(sample: dict, result: dict, scores: dict) -> str | None:
    """返回 D1–D9 归因编码；无失败/不可诊断时返回 None。"""
    error = (result or {}).get("error")
    if error:
        return "D9"
    gold = str(sample.get("gold_answer") or "").strip()
    answer = str((result or {}).get("answer") or "").strip()
    score = (scores or {}).get("score")
    if not gold:
        # 无金标准（如仅需拒答或样本缺陷），交人工确认，不强行归因
        return "D6" if not answer else None
    if score is not None and score >= 0.5:
        return None  # 通过
    retrieved = (result or {}).get("retrieved")
    if retrieved is None:
        # 待测系统未返回检索轨迹 → 有限端到端评估，标记不可诊断检索层
        return None
    if not retrieved:
        return "D3"  # 检索召回失败
    return "D5"  # 证据已在上下文但答案生成失败（基础版；D6 交人工确认）
