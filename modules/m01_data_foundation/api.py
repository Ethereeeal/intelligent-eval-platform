from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from modules.m01_data_foundation.schemas import (
    BlockOut,
    CorpusCreate,
    CorpusOut,
    DocumentOut,
    DocumentUploadResponse,
    JobOut,
    ReuploadResponse,
)
from modules.m01_data_foundation.services.pipeline import PipelineService

documents_router = APIRouter(prefix="/api/documents", tags=["documents"])
corpus_router = APIRouter(prefix="/api/corpus", tags=["corpus"])
jobs_router = APIRouter(prefix="/api/jobs", tags=["jobs"])

pipeline_service = PipelineService()


# ----------------------------------------------------------------------
# 语料库
# ----------------------------------------------------------------------
@corpus_router.post("", response_model=CorpusOut)
def create_corpus(payload: CorpusCreate):
    corpus_id = pipeline_service.create_corpus(
        name=payload.name,
        description=payload.description,
        domain=payload.domain,
        created_by=payload.created_by,
    )
    return pipeline_service.get_corpus(corpus_id)


@corpus_router.get("", response_model=list[CorpusOut])
def list_corpora():
    return pipeline_service.list_corpora()


@corpus_router.get("/{corpus_id}", response_model=CorpusOut)
def get_corpus(corpus_id: int):
    corpus = pipeline_service.get_corpus(corpus_id)
    if corpus is None:
        raise HTTPException(status_code=404, detail="corpus not found")
    return corpus


# ----------------------------------------------------------------------
# 文档接入
# ----------------------------------------------------------------------
@documents_router.post("/upload", response_model=DocumentUploadResponse)
def upload_document(
    corpus_id: int = Form(...),
    upload_user: str | None = Form(None),
    document_version: str | None = Form(None),
    file: UploadFile = File(...),
):
    content = file.file.read()
    try:
        result = pipeline_service.upload_document(
            minio_path="",  # 由 pipeline 内部存储后回填路径
            file_name=file.filename or "upload.bin",
            file_type=file.filename or "",
            content=content,
            corpus_id=corpus_id,
            upload_user=upload_user,
            document_version=document_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DocumentUploadResponse(**result)


@documents_router.get("", response_model=list[DocumentOut])
def list_documents(corpus_id: int | None = None):
    return pipeline_service.list_documents(corpus_id)


@documents_router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: int):
    document = pipeline_service.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return document


@documents_router.get("/{document_id}/blocks", response_model=list[BlockOut])
def get_document_blocks(document_id: int):
    if pipeline_service.get_document(document_id) is None:
        raise HTTPException(status_code=404, detail="document not found")
    return pipeline_service.get_document_blocks(document_id)


@documents_router.post("/{document_id}/reupload", response_model=ReuploadResponse)
def reupload_document(document_id: int, file: UploadFile = File(...)):
    content = file.file.read()
    try:
        result = pipeline_service.reupload_document(
            document_id=document_id,
            content=content,
            file_name=file.filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReuploadResponse(**result)


# ----------------------------------------------------------------------
# 任务进度
# ----------------------------------------------------------------------
@jobs_router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int):
    job = pipeline_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
