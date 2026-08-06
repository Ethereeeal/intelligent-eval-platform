"""M02 — EIU 抽取与覆盖规划：请求 / 响应 Pydantic 模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class EiuExtractResponse(BaseModel):
    """POST /api/corpus/{corpus_id}/eiu/extract — 异步触发成功响应（202）。"""

    job_id: int
    corpus_id: int
    status: str
    message: str


class EiuOut(BaseModel):
    eiu_id: int
    corpus_id: int
    block_id: int
    document_id: int | None = None
    document_name: str | None = None
    section_path: str | None = None
    statement: str
    eiu_type: str
    content_priority: str
    weight: int
    constraints: dict | None = None
    evidence_blocks: list[int] | None = None
    is_questionable: bool
    exclusion_reason: str | None = None
    extraction_model: str | None = None
    extraction_confidence: float | None = None
    review_status: str
    created_at: str | None = None


class EiuListResponse(BaseModel):
    corpus_id: int
    total: int
    items: list[EiuOut]


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
    extraction_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


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
    corpus_id: int
    total_eiu: int
    questionable_eiu: int
    excluded_eiu: int
    by_priority: dict[str, int]
    by_type: dict[str, int]
    by_document: list[dict]
    by_section: list[dict]
    weighted_coverage: float
    p0_coverage_pct: float
    block_reconciliation: BlockReconciliation
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
    corpus_id: int
    total: int
    items: list[GapItem]


class CoverageReportOut(CoverageReport):
    """持久化后的覆盖率报告（含 report_id / created_at）。"""

    report_id: int
    created_at: str | None = None
