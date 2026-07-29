from typing import Any

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    document_id: int
    task_id: int
    status: str
    file_name: str
    block_count: int


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    corpus_id: int | None = None
    top_k: int = Field(default=3, ge=1, le=20)


class SearchHit(BaseModel):
    block_id: int
    score: float
    source_excerpt: str
    document_id: int
    section_path: str | None = None


class QueryResponse(BaseModel):
    question: str
    corpus_id: int | None
    hits: list[SearchHit]
    answer: str
    debug: dict[str, Any] = Field(default_factory=dict)
