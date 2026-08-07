"""m03 评测集生成：Prompt 模板。

README §2.3 说明：题目与答案提示词分列仅为约束聚焦（题目侧关注
"不泄露答案、表述规范"，答案侧关注"仅基于原文、必中要点、绑定证据"），
实际在一次 LLM 调用中合并输出完整 JSON。
"""
from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# 常量：题型映射、难度规则、证据上下文窗口
# ---------------------------------------------------------------------------

# EIU 类型 → 题目类型（README §2.2 题型映射表）
EIU_TYPE_TO_QUESTION_TYPE: dict[str, str] = {
    "definition": "definition",    # 定义题
    "rule": "rule",                # 条件与适用范围题
    "threshold": "threshold",      # 阈值和数值题
    "date": "date",                # 时效题
    "formula": "formula",          # 公式与计算题
    "process": "process",          # 流程顺序题
    "exception": "exception",      # 例外与边界题
    "prohibition": "prohibition",  # 是否可回答题
    "metric": "metric",            # 事实提取题
    "change": "change",            # 比较与区分题
}

# 默认出题角度（README §2.2 Demo 约束：多角度对同一 EIU 提问）
DEFAULT_ANGLES: list[str] = [
    "primary",          # 规范主问法（默认题型模板）
    "value_lookup",     # 取值查询角度
    "condition",        # 条件判断角度
    "process",          # 流程步骤角度
    "definition",       # 定义解释角度
    "exception",        # 例外边界角度
    "comparison",       # 对比区分角度
]

# 答案侧 JSON 键列表（README §2.3 答案 Prompt 输出字段）
ANSWER_KEYS: list[str] = [
    "gold_answer",
    "must_have_points",
    "acceptable_answers",
    "evidence_bindings",
    "is_unanswerable",
]

# 动态上下文筛选（README §2.1 第 2 步）：
# - CONTEXT_WINDOW：位置兜底窗口，源块前后各取 N 个相邻块（术语延续性）
# - SEMANTIC_TOP_K：语义召回数，以 EIU 内容为 query 检索最相关块
# - MAX_CONTEXT_BLOCKS：预算上限，合并去重后截断到该块数（相关性优先）
CONTEXT_WINDOW = 1
SEMANTIC_TOP_K = 3
MAX_CONTEXT_BLOCKS = 5


# ---------------------------------------------------------------------------
# Prompt 构建
# ---------------------------------------------------------------------------

def build_qa_prompt(
    *,
    statement: str,
    eiu_type: str,
    question_type: str,
    angle: str,
    context: list[dict],
    block_text: str,
    section_path: str,
    page_no: str | None,
    constraints: dict[str, Any] | None,
    difficulty_hint: str | None = None,
) -> str:
    """合并题目+答案的单一生成 Prompt（README §2.1 / §2.3）。

    题目侧约束：仅凭材料可答、不自带前提、不泄露答案、正式书面、
    不含"根据上文/根据材料"等提示语。
    答案侧约束：仅基于原文、列出必须命中要点、可接受同义表达、
    每个要点绑定原文证据；原文证据不足时 is_unanswerable=true。
    """
    context_text = _render_context(context)
    constraints_text = json.dumps(constraints, ensure_ascii=False) if constraints else "无"
    angle_desc = _angle_description(angle, question_type)

    return (
        "你是一个评测集编制专家，负责为授信政策、财务报告等文档生成"
        "『规范问题 + 标准答案 + 证据绑定』。\n"
        "题目与答案在同一次回复中一并输出，严格返回 JSON，不要输出任何额外文字。\n\n"
        "【输入信息】\n"
        f"- 待出题陈述（EIU）：{statement}\n"
        f"- EIU 类型：{eiu_type}\n"
        f"- 目标题型：{question_type}\n"
        f"- 出题角度：{angle_desc}\n"
        f"- 原文定位：章节路径「{section_path}」 页码「{page_no or '未知'}」\n"
        f"- 限定信息（主体/条件/期间/币种/单位等）：{constraints_text}\n"
        f"- 原文证据 Block：\n{block_text}\n"
        f"- 相邻上下文 Block（辅助理解，不可作为题面主体）：\n{context_text}\n\n"
        "【题目生成约束】\n"
        "1. 问题仅凭以上材料即可回答，不引入材料之外的前提；\n"
        "2. 不自带答案、不泄露答案线索；\n"
        "3. 正式书面表达，避免口语；\n"
        "4. 不包含『根据上文』『根据材料』『请结合材料』等提示语；\n"
        "5. 一条问题只问一个核心事实。\n\n"
        "【答案生成约束】\n"
        "1. 答案仅基于原文证据，不补充常识；\n"
        "2. must_have_points 列出所有必须命中的答案要点（字符串数组）；\n"
        "3. acceptable_answers 列出可接受的同义表达（字符串数组）；\n"
        "4. evidence_bindings 为数组，每项 {must_have_point, evidence}，"
        "evidence 含 document_id/document_name/section_path/page_no/"
        "block_id/original_text/start_offset/end_offset；\n"
        "5. 原文证据不足以支撑规范答案时，is_unanswerable=true，"
        "并在 gold_answer 中说明缺什么，绝不伪造答案。\n"
        "6. difficulty 取值 L1/L2/L3：L1=单段直接事实；L2=条件推理/二跳/轻微消歧；"
        "L3=跨段多跳/计算+消歧/对抗（本场景为单段题，默认 L1 或 L2）。\n\n"
        "【输出 JSON 字段】\n"
        '{"question": string, "question_type": string, "difficulty": "L1"|"L2"|"L3", '
        '"gold_answer": string, "must_have_points": [string], '
        '"acceptable_answers": [string], "evidence_bindings": ['
        '{"must_have_point": string, "evidence": {document_id, document_name, '
        'section_path, page_no, block_id, original_text, start_offset, end_offset}}], '
        '"is_unanswerable": bool}'
    )


def build_variation_prompt(
    *,
    question: str,
    gold_answer: str,
    must_have_points: list[str],
    acceptable_answers: list[str],
    styles: list[str],
) -> str:
    """泛化/改写扩写 Prompt（README §2.6 模式 B 泛化 + §4.1 FR-VAR-001/002）。

    以种子问答对为输入，产出多种表述变体；所有变体共享同一意图与标准答案。
    """
    styles_text = "\n".join(f"- {style}: {_style_description(style)}" for style in styles)
    return (
        "你是一个评测集改写专家。请基于下面的种子问答对，生成若干"
        "『表述不同、原意相同』的相关问题变体。\n"
        "严格返回 JSON 数组，不要输出额外文字。\n\n"
        "【种子问题】\n" + question + "\n\n"
        "【标准答案】\n" + gold_answer + "\n\n"
        "【必须命中要点】\n" + json.dumps(must_have_points, ensure_ascii=False) + "\n\n"
        "【可接受同义表达】\n" + json.dumps(acceptable_answers, ensure_ascii=False) + "\n\n"
        "【变体风格要求】\n" + styles_text + "\n\n"
        "【改写约束】\n"
        "1. 原意不变：新问题与原问题指向同一事实、同一答案；\n"
        "2. 不引入原文不存在的新前提、不产生新歧义；\n"
        "3. 不包含『根据上文』『根据材料』等提示语；\n"
        "4. 各变体之间表述差异要明显，避免近义重复；\n"
        "5. 所有变体共享本种子题的意图与标准答案，不改变答案要点。\n\n"
        "【输出 JSON 数组】\n"
        '[{"question": string, "variation_style": string, "note": string}]'
    )


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _render_context(context: list[dict]) -> str:
    if not context:
        return "（无相邻上下文）"
    lines = []
    for index, block in enumerate(context):
        lines.append(
            f"[{index}] 章节「{block.get('section_path', '未分类')}」"
            f" 页码「{block.get('page_no') or '未知'}」：{block.get('block_text', '')[:300]}"
        )
    return "\n".join(lines)


def _angle_description(angle: str, question_type: str) -> str:
    descriptions: dict[str, str] = {
        "primary": f"按题型模板『{question_type}』的标准问法",
        "value_lookup": "取值查询角度：问指标/阈值/日期的具体数值或取值",
        "condition": "条件判断角度：给定场景判断是否满足条件、适用规则",
        "process": "流程步骤角度：要求列出完整流程或步骤顺序",
        "definition": "定义解释角度：要求给出术语或规则的完整定义",
        "exception": "例外边界角度：询问例外的适用情形与边界",
        "comparison": "对比区分角度：要求对比新旧版本、不同主体或相近概念",
    }
    return descriptions.get(angle, "标准问法")


def _style_description(style: str) -> str:
    descriptions: dict[str, str] = {
        "formal": "正式书面表达",
        "colloquial": "简短口语化表达",
        "omitted_subject": "省略主语（上下文已明确主体）",
        "term_abbrev": "使用术语全称/简称的另一种写法",
        "reordered": "调整语序但不改变语义",
        "with_context": "在问题中加入无关背景铺垫",
        "scene_first": "先描述使用场景再提问",
        "related_followup": "生成追问/对比/边界等关联问题（仍基于同一答案要点）",
    }
    return descriptions.get(style, style)
