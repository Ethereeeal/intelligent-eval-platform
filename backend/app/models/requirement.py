"""Requirement & test function point data models."""
from dataclasses import dataclass


@dataclass
class RequirementDocRecord:
    requirement_doc_id: int
    corpus_id: int | None
    file_name: str
    file_type: str
    requirement_version: str | None
    business_domain: str | None
    parse_status: str
    uploaded_at: str


@dataclass
class TestFunctionPointRecord:
    tfp_id: int
    requirement_doc_id: int
    section_path: str
    requirement_id: str | None
    statement: str
    eiu_type: str
    content_priority: str
    weight: int
    evidence_range: str  # JSON list
    is_questionable: bool
    exclusion_reason: str | None
    extraction_confidence: float
    review_status: str
    created_at: str
