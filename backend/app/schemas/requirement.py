"""Requirement & test function point schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RequirementUploadResponse(BaseModel):
    """Response after uploading a business requirement document."""
    requirement_doc_id: int
    file_name: str
    status: str
    message: str = ""


class TestFunctionPoint(BaseModel):
    """A single test function point (EIU) extracted from a requirement doc."""
    tfp_id: int
    requirement_doc_id: int
    section_path: str
    requirement_id: str | None = None
    statement: str
    eiu_type: str  # "functional_rule" | "business_rule" | "data_rule" | "interface_rule" | "nfr"
    content_priority: str  # "P0" | "P1" | "P2"
    weight: int = 1
    evidence_range: list[str] = Field(default_factory=list)
    is_questionable: bool = True
    exclusion_reason: str | None = None
    extraction_confidence: float = 0.0
    review_status: str = "candidate"
    created_at: datetime | None = None


class TestFunctionPointListResponse(BaseModel):
    """Paginated list of test function points."""
    requirement_doc_id: int
    total_count: int
    items: list[TestFunctionPoint] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)  # coverage stats by section/priority


class RequirementDocResponse(BaseModel):
    """Requirement document metadata."""
    requirement_doc_id: int
    corpus_id: int | None = None
    file_name: str
    file_type: str
    requirement_version: str | None = None
    business_domain: str | None = None
    parse_status: str
    uploaded_at: datetime | None = None


class ExtractRequest(BaseModel):
    """Request to trigger EIU extraction from a requirement document."""
    pass  # Demo: no extra params; MVP may add rule-set version etc.
