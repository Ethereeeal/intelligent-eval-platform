"""m03 评测集生成：API 数据契约（请求/响应模型）。

对应 README §2.5 数据模型与 §6 API 接口。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# 枚举常量（与 README 2.2 / 5.1 一致）
QUESTION_TYPES = Literal[
    "definition", "rule", "threshold", "date", "formula",
    "process", "exception", "prohibition", "metric", "change",
]
DIFFICULTY_LEVELS = Literal["L1", "L2", "L3"]
PRIORITY_LEVELS = Literal["P0", "P1", "P2"]
SCOPE_TYPES = Literal["single_segment", "cross_segment"]
REVIEW_STATUS = Literal[
    "candidate", "needs_review", "quality_verified",
    "governance_passed", "published", "retired",
]

# 默认允许的题目角度（README 2.2 Demo 约束：多角度对同一 EIU 提问）
DEFAULT_ANGLES: list[str] = ["primary"]


class GenerateCasesRequest(BaseModel):
    """批量生成请求体。"""

    angles: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ANGLES),
        description="出题角度列表，每个角度对同一 EIU 生成一道题（不重复计覆盖率）。"
        "支持: primary / value_lookup / condition / process / definition / "
        "exception / comparison 等",
    )
    include_variations: bool = Field(
        default=False,
        description="生成规范题后是否附带一次泛化改写扩写",
    )
    variation_count: int = Field(default=2, ge=0, le=10, description="每个种子的泛化变体数量")
    dry_run: bool = Field(
        default=False,
        description="true 时仅返回待生成 EIU 清单，不实际调用 LLM / 落库",
    )


class GenerateSingleCaseRequest(BaseModel):
    """单个 EIU 生成请求。"""

    angle: str = Field(default="primary", description="出题角度（见 GenerateCasesRequest.angles）")
    include_variations: bool = False
    variation_count: int = Field(default=2, ge=0, le=10)


class EvidenceBinding(BaseModel):
    """FR-QG-003 证据绑定：must_have_point ↔ 底层原文证据。"""

    must_have_point: str
    evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="含 document_id/document_name/section_path/page_no/"
        "block_id/original_text/start_offset/end_offset",
    )


class CaseOut(BaseModel):
    """评测样本输出（列表项）。"""

    case_id: int
    intent_id: str
    eiu_id: int | None = None
    corpus_id: int
    document_id: int | None = None
    question: str
    question_type: str
    difficulty: str
    scope_type: str
    gold_answer: str
    must_have_points: list[str] | None = None
    acceptable_answers: list[str] | None = None
    evidence: list[dict] | None = None
    content_priority: str
    review_status: str
    created_at: str | None = None
    updated_at: str | None = None


class CaseDetailOut(CaseOut):
    """样本详情（含完整证据定位），在 CaseOut 基础上扩展。"""

    pass


class CaseUpdateRequest(BaseModel):
    """手动编辑样本请求（PUT）。"""

    question: str | None = None
    question_type: QUESTION_TYPES | None = None
    difficulty: DIFFICULTY_LEVELS | None = None
    gold_answer: str | None = None
    must_have_points: list[str] | None = None
    acceptable_answers: list[str] | None = None
    evidence: list[EvidenceBinding] | None = None
    review_status: REVIEW_STATUS | None = None


class UploadQAPairRequest(BaseModel):
    """路径 2：用户直接上传问答对（种子），经校验后进入泛化。"""

    corpus_id: int
    document_id: int | None = None
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    question_type: QUESTION_TYPES = "rule"
    difficulty: DIFFICULTY_LEVELS = "L2"
    content_priority: PRIORITY_LEVELS = "P2"
    evidence: list[EvidenceBinding] | None = None
    generate_variations: bool = Field(
        default=False, description="上传后是否立即泛化出相关问题对"
    )
    variation_count: int = Field(default=2, ge=0, le=10)


class VariationRequest(BaseModel):
    """对既有种子题做泛化/改写扩写。"""

    case_id: int = Field(..., description="种子题（规范题或用户上传题）")
    count: int = Field(default=3, ge=1, le=10, description="生成的变体数量")
    styles: list[str] = Field(
        default_factory=lambda: ["formal", "colloquial", "omitted_subject", "reordered"],
        description="改写风格: formal/colloquial/omitted_subject/term_abbrev/"
        "reordered/with_context/scene_first/related_followup",
    )


class GeneratedCaseResult(BaseModel):
    """单个 EIU 生成结果。"""

    eiu_id: int
    eiu_type: str
    statement: str
    case_ids: list[int] = Field(default_factory=list)
    variation_case_ids: list[int] = Field(default_factory=list)
    error: str | None = None


class GenerateCasesResponse(BaseModel):
    """批量生成响应。"""

    corpus_id: int
    total_questionable_eiu: int
    already_covered: int = 0
    generated: int = 0
    failed: int = 0
    results: list[GeneratedCaseResult] = Field(default_factory=list)
    pending_eius: list[EiuBrief] = Field(
        default_factory=list,
        description="dry_run=true 时返回的待生成 EIU 预览清单",
    )


class EiuBrief(BaseModel):
    """dry_run 模式下返回的待生成 EIU 清单项。"""

    eiu_id: int
    eiu_type: str
    content_priority: str
    statement: str
