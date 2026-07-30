from __future__ import annotations

from pydantic import BaseModel


class CorpusCreate(BaseModel):
    name: str
    description: str | None = None
    domain: str | None = None
    created_by: str | None = None


class CorpusOut(BaseModel):
    corpus_id: int
    name: str
    description: str | None = None
    domain: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    version: str | None = None


class DocumentUploadRequest(BaseModel):
    corpus_id: int
    upload_user: str | None = None
    document_version: str | None = None


class DocumentUploadResponse(BaseModel):
    document_id: int
    duplicate: bool = False
    blocks: int = 0


class ReuploadResponse(BaseModel):
    job_id: int
    document_id: int
    changed: bool = False


class DocumentOut(BaseModel):
    document_id: int
    corpus_id: int
    file_name: str
    file_type: str
    file_size: int | None = None
    parse_status: str | None = None
    status: str
    created_at: str | None = None


class BlockOut(BaseModel):
    block_id: int
    document_id: int
    parent_block_id: int | None = None
    section_path: str
    page_no: str | None = None
    block_type: str
    block_text: str
    start_offset: int | None = None
    end_offset: int | None = None
    metadata_json: dict | None = None


class JobOut(BaseModel):
    job_id: int
    corpus_id: int
    document_id: int
    job_type: str
    status: str
    phase: str | None = None
    progress: int = 0
    message: str | None = None
    created_at: str | None = None
    finished_at: str | None = None
