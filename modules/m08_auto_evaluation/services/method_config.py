"""评测任务类型、可选方法及其标准引用元数据。"""
from __future__ import annotations

from collections.abc import Sequence

TASK_PROFILE_LABELS = {
    "question_answering": "通用问答",
    "translation": "翻译",
    "text_generation": "文本生成",
}

METHOD_LABELS = {
    "answer_comparison": "标准答案比对（精确匹配 / 语义相似度）",
    "rules": "规则评测",
    "llm_as_judge": "LLM-as-a-Judge",
    "bleu": "BLEU",
    "rouge_l": "ROUGE-L",
}

METHOD_STANDARD_LABELS = {
    "answer_comparison": "项目方法",
    "rules": "项目方法",
    "llm_as_judge": "标准提及的评测方法（非指标）",
    "bleu": "GB/T 45288.2—2025 附录 A.1.5 公式",
    "rouge_l": "GB/T 45288.2—2025 附录 A.1.6 公式",
}

DEFAULT_EVALUATION_METHODS = ("answer_comparison", "rules")
SUPPORTED_METHODS = tuple(METHOD_LABELS)


def normalize_evaluation_selection(
    task_profile: str | None,
    methods: Sequence[str] | None,
    *,
    legacy_judge_enabled: bool = False,
) -> dict:
    """规范化单次运行的任务类型和方法；缺省请求沿用旧版评分行为。"""
    profile = str(task_profile or "question_answering").strip().lower()
    if profile not in TASK_PROFILE_LABELS:
        raise ValueError(f"不支持的任务类型: {profile}")

    if methods is None:
        normalized = list(DEFAULT_EVALUATION_METHODS)
        if legacy_judge_enabled:
            normalized.append("llm_as_judge")
    else:
        if isinstance(methods, (str, bytes)):
            raise ValueError("evaluation_methods 必须是数组")
        normalized = []
        for value in methods:
            method = str(value).strip().lower()
            if method not in SUPPORTED_METHODS:
                raise ValueError(f"不支持的评测方法: {method}")
            if method not in normalized:
                normalized.append(method)

    if "bleu" in normalized and profile != "translation":
        raise ValueError("BLEU 仅适用于翻译任务")
    if "rouge_l" in normalized and profile != "text_generation":
        raise ValueError("ROUGE-L 仅适用于文本生成任务")
    return {"task_profile": profile, "evaluation_methods": normalized}
