"""M02 — EIU 抽取与覆盖规划：请求 / 响应 Pydantic 模型（按文件维度，无 corpus）。"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field
from pydantic import field_validator


class EiuExtractResponse(BaseModel):
    """POST /api/eiu/extract — 异步触发成功响应（202）。"""

    job_id: int
    status: str
    message: str


class EiuOut(BaseModel):
    eiu_id: int
    block_id: int
    document_id: int | None = None
    document_name: str | None = None
    section_path: str | None = None
    statement: str
    eiu_type: str
    content_priority: str
    weight: int
    constraints: dict | None = None
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    modality: str | None = None
    qualifiers: dict | None = None
    evidence_blocks: list[int] | None = None
    evidence_details: list[dict] | None = None
    is_questionable: bool
    exclusion_reason: str | None = None
    extraction_model: str | None = None
    extraction_confidence: float | None = None
    review_status: str
    quality_status: str = "candidate"
    quality_score: float | None = None
    quality_checks: dict | None = None
    complexity_level: str | None = None
    complexity_score: float | None = None
    complexity_factors: dict | None = None
    route_color: str | None = None
    route_reasons: list[str] | None = None
    review_action: str | None = None
    review_attempts: int = 0
    review_model: str | None = None
    review_prompt_version: str | None = None
    source_candidate_ids: list[int] | None = None
    source_eiu_ids: list[int] | None = None
    importance_signals: list[str] | None = None
    importance_reason: str | None = None
    canonical_intent_key: str | None = None
    auto_disposition: str | None = None
    quality_policy_version: str | None = None
    evaluation_profiles: list[str] | None = None
    manual_include: bool = False
    manual_include_reason: str | None = None
    created_at: str | None = None


class EiuListResponse(BaseModel):
    total: int
    items: list[EiuOut]

    model_config = {"exclude_none": True}


class EiuDetail(EiuOut):
    """EIU 详情，追加原文上下文。"""

    context: dict | None = None


class EiuUpdate(BaseModel):
    """PUT /api/eiu/{eiu_id} — 全字段可选，仅更新传入字段。"""

    statement: str | None = Field(default=None, max_length=200, description="完整陈述（≤200 字）")
    eiu_type: str | None = None
    content_priority: str | None = None
    is_questionable: bool | None = None
    exclusion_reason: str | None = Field(default=None, max_length=128)
    constraints: dict | None = None
    subject: str | None = Field(default=None, max_length=256)
    predicate: str | None = Field(default=None, max_length=128)
    object: str | None = Field(default=None, max_length=2000)
    modality: str | None = Field(default=None, max_length=64)
    qualifiers: dict | None = None
    extraction_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    quality_status: Literal["candidate", "verified", "needs_review", "rejected"] | None = None

    @field_validator("constraints")
    @classmethod
    def validate_constraints_size(cls, value: dict | None) -> dict | None:
        if value is None:
            return None
        if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 16 * 1024:
            raise ValueError("constraints 不能超过 16KB")
        return value

    @field_validator("qualifiers")
    @classmethod
    def validate_qualifiers_size(cls, value: dict | None) -> dict | None:
        if value is None:
            return None
        if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 16 * 1024:
            raise ValueError("qualifiers 不能超过 16KB")
        return value


class EiuManualIncludeRequest(BaseModel):
    """人工指定纳入仅是用途选择覆盖，不覆盖系统质量与重要性结论。"""

    reason: str = Field(min_length=2, max_length=500)


class EiuMergeRequest(BaseModel):
    source_eiu_ids: list[int] = Field(min_length=2, max_length=20)
    statement: str = Field(min_length=4, max_length=200)


class EiuSplitRequest(BaseModel):
    statements: list[str] = Field(min_length=2, max_length=10)

    @field_validator("statements")
    @classmethod
    def validate_statements(cls, value: list[str]) -> list[str]:
        cleaned = [statement.strip() for statement in value if statement and statement.strip()]
        if len(set(cleaned)) < 2:
            raise ValueError("至少需要两条不同的非空知识点")
        if any(len(statement) > 200 for statement in cleaned):
            raise ValueError("单条知识点不能超过 200 字")
        return cleaned


class DeleteResponse(BaseModel):
    eiu_id: int
    status: str
    review_status: str


class BlockReconciliation(BaseModel):
    total_paragraph_blocks: int
    covered_blocks: int
    rate: float
    uncovered_blocks: list[dict] = Field(default_factory=list)


class CoverageReport(BaseModel):
    total_eiu: int
    questionable_eiu: int
    excluded_eiu: int
    candidate_eiu: int = 0
    verified_eiu: int = 0
    needs_review_eiu: int = 0
    rejected_eiu: int = 0
    by_priority: dict[str, int]
    by_type: dict[str, int]
    by_document: list[dict]
    by_section: list[dict]
    weighted_coverage: float
    p0_coverage_pct: float
    block_reconciliation: BlockReconciliation
    claim_relation_summary: dict = Field(default_factory=dict)
    document_audit: list[dict] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)


class GapItem(BaseModel):
    eiu_id: int
    block_id: int
    section_path: str | None = None
    statement: str
    eiu_type: str
    content_priority: str
    weight: int
    reason: str = "暂无对应题目"


class GapListResponse(BaseModel):
    total: int
    items: list[GapItem]


class CoverageReportOut(CoverageReport):
    """持久化后的覆盖率报告（含 report_id / created_at）。"""

    report_id: int
    created_at: str | None = None
