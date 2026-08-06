"""m04 质量门禁：质量校验 Prompt 模板。

README §2.1 的 5 项基础检查（含问题相关性）：
  #1 answerability           可回答性：材料是否含完整答案所需全部信息
  #2 faithfulness            答案忠实性：答案每个要点是否被原文证据支持
  #3 uniqueness              唯一性：是否存在多个同样合理的答案未被纳入
  #4 evidence_sufficiency    证据充分性：证据是否完整覆盖答案所有要点
  #5 question_relevance      问题相关性：问题是否扎根文档/与原文主题相关

一次 LLM 调用同时产出 5 项结论，逐项 passed/failed + reason。
"""
from __future__ import annotations

import json
from typing import Any

# 5 项检查的固定顺序（README §2.1 表格顺序）
CHECK_TYPES: list[str] = [
    "answerability",
    "faithfulness",
    "uniqueness",
    "evidence_sufficiency",
    "question_relevance",
]

CHECK_TYPE_DESCRIPTIONS: dict[str, str] = {
    "answerability": "可回答性：给定原文材料，判断能否完整回答题目；若材料缺少必要信息则 failed",
    "faithfulness": "答案忠实性：答案的每个要点是否被原文证据支持；逐要点核对原文，检测幻觉/捏造，"
    "任一要点无原文支持则 failed",
    "uniqueness": "唯一性：是否存在多个同样合理的答案未被纳入；若存在漏收的合理答案则 failed",
    "evidence_sufficiency": "证据充分性：已绑定证据是否完整覆盖答案所有要点，而不只是关键词命中；"
    "证据缺失/覆盖不全则 failed",
    "question_relevance": "问题相关性：题目是否由该文档/EIU 内容合理导出、与原文主题相关；"
    "问题提及的实体/概念是否确实出现在原文中；臆造无关/偏离主题则 failed",
}


def build_quality_check_prompt(
    *,
    question: str,
    gold_answer: str,
    must_have_points: list[str],
    acceptable_answers: list[str],
    evidence: list[dict],
    source_context: str | None,
) -> str:
    """构建单题 5 项质量检查 Prompt。

    evidence: 该 case 的证据绑定列表（含 original_text / section_path / page_no）。
    source_context: 原文上下文摘要（EIU 陈述 + 证据原文），问题相关性检查的依据。
    """
    points_text = json.dumps(must_have_points, ensure_ascii=False) if must_have_points else "（无）"
    acceptable_text = (
        json.dumps(acceptable_answers, ensure_ascii=False) if acceptable_answers else "（无）"
    )
    evidence_text = _render_evidence(evidence)
    context_text = source_context or "（无原文上下文）"

    rules = "\n".join(
        f"{index + 1}. {CHECK_TYPE_DESCRIPTIONS[check_type]}"
        for index, check_type in enumerate(CHECK_TYPES)
    )

    return (
        "你是一个评测集质量审核专家，负责对评测样本执行 5 项基础质量检查。\n"
        "请逐项判断，严格返回 JSON，不要输出任何额外文字。\n\n"
        "【待检查题目】\n" + question + "\n\n"
        "【标准答案】\n" + gold_answer + "\n\n"
        "【必须命中要点】\n" + points_text + "\n\n"
        "【可接受同义表达】\n" + acceptable_text + "\n\n"
        "【已绑定原文证据】\n" + evidence_text + "\n\n"
        "【原文上下文（检查问题相关性依据）】\n" + context_text + "\n\n"
        "【5 项检查规则】\n" + rules + "\n\n"
        "【输出 JSON 字段】\n"
        '{"checks": [{"check_type": "answerability|faithfulness|uniqueness|'
        'evidence_sufficiency|question_relevance", "passed": bool, '
        '"reason": string}, ...]}\n'
        "要求：\n"
        "1. 5 项检查必须全部输出，check_type 严格使用上述枚举；\n"
        "2. passed=true 时 reason 简述判断依据；passed=false 时 reason 说明具体失败原因；\n"
        "3. 忠实于原文，不因题目生成自该文档就默认放行。"
    )


def build_retry_reason_hint() -> str:
    """（预留）重跑时的提示语占位。"""
    return ""


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _render_evidence(evidence: list[dict]) -> str:
    if not evidence:
        return "（无证据绑定）"
    lines: list[str] = []
    for index, binding in enumerate(evidence):
        ev = binding.get("evidence") or {}
        point = binding.get("must_have_point") or ""
        text = ev.get("original_text") or ""
        location = (
            f"章节「{ev.get('section_path', '未分类')}」"
            f"页码「{ev.get('page_no') or '未知'}」block {ev.get('block_id')}"
        )
        lines.append(
            f"[{index + 1}] 要点「{point}」\n"
            f"    定位：{location}\n"
            f"    原文：{text[:400]}"
        )
    return "\n\n".join(lines)
