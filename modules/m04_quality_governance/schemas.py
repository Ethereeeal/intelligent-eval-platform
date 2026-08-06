"""m04 质量门禁：API 数据契约（请求/响应模型）。

对应 README §2.2 校验流程 / §2.3 汇总响应 / §4 API 接口。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 5 项基础检查（README §2.1，含问题相关性）
CHECK_TYPES = Literal[
    "answerability",          # 可回答性
    "faithfulness",           # 答案忠实性
    "uniqueness",             # 唯一性
    "evidence_sufficiency",   # 证据充分性
    "question_relevance",     # 问题相关性（问题扎根文档）
]

CHECK_TYPE_LABELS: dict[str, str] = {
    "answerability": "可回答性",
    "faithfulness": "答案忠实性",
    "uniqueness": "唯一性",
    "evidence_sufficiency": "证据充分性",
    "question_relevance": "问题相关性",
}

# 待人工确认时的失败原因标签（review_tag）
#   answer_coverage   答案/证据覆盖度待人工复核（soft 失败，不自动重生成）
#   generation_issue  题目生成有问题（hard 失败，自动重生成多次仍失败）
REVIEW_TAGS = Literal["answer_coverage", "generation_issue"]

REVIEW_TAG_LABELS: dict[str, str] = {
    "answer_coverage": "答案/证据覆盖度待人工复核",
    "generation_issue": "题目生成有问题，自动重生成未通过",
}

# 硬性失败：题目本身质量有问题 → 自动回 m03 重生成
HARD_CHECKS = ("faithfulness", "question_relevance")
# 软性失败：覆盖度/唯一性需人工确认 → 不自动重生成
SOFT_CHECKS = ("evidence_sufficiency", "uniqueness")


class QualityCheckResultOut(BaseModel):
    """单条检查结果（README §2.3 quality_check_result 表行）。"""

    check_id: int
    case_id: int
    check_type: CHECK_TYPES
    passed: bool
    reason: str
    checked_at: str | None = None


class QualityCheckSummary(BaseModel):
    """校验结果汇总 API 响应（README §2.3 示例 JSON）。"""

    corpus_id: int
    total_cases: int = Field(default=0, description="参与本轮校验的样本数")
    passed: int = 0
    failed: int = 0
    by_check_type: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="各检查项 {passed: n, failed: m} 统计",
    )
    failed_cases: list[dict] = Field(
        default_factory=list,
        description="失败样本列表: {case_id, failed_checks, reason, review_tag}",
    )


class CaseQualityDetail(BaseModel):
    """单题校验详情（GET /api/cases/{case_id}/quality-check）。"""

    case_id: int
    question: str
    gold_answer: str
    review_status: str
    review_tag: str | None = None
    passed: bool
    checks: list[QualityCheckResultOut] = Field(default_factory=list)


class RetryCheckResult(BaseModel):
    """单题重跑校验结果（POST /api/cases/{case_id}/retry-check）。

    replaced_case_id: hard 失败自动重生成成功时，原 case 退役、新 case
    替代；本字段指向新 case。此时 review_status 为 "retired"（原 case）。
    """

    case_id: int
    replaced_case_id: int | None = None
    passed: bool
    review_status: str
    review_tag: str | None = None
    checks: list[QualityCheckResultOut] = Field(default_factory=list)
