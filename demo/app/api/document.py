from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.document import DocumentUploadResponse, QueryRequest, QueryResponse
from app.services.pipeline import PipelineService

router = APIRouter(prefix="/api")
service = PipelineService()


@router.post("/corpus", response_model=dict)
def create_corpus(name: str = Form(...), description: str | None = Form(None), domain: str | None = Form(None)) -> dict:
    return service.create_corpus(name=name, description=description, domain=domain)


@router.get("/corpus", response_model=list[dict])
def list_corpora() -> list[dict]:
    return service.list_corpora()


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    corpus_id: int = Form(...),
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    try:
        content = await file.read()
        return service.upload_document(
            file_name=file.filename or "uploaded_file",
            file_type=file.content_type or "application/octet-stream",
            corpus_id=corpus_id,
            content=content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/documents/{document_id}/extract_eius", response_model=dict)
def extract_eius(document_id: int, corpus_id: int) -> dict:
    return service.extract_eius_for_document(document_id=document_id, corpus_id=corpus_id)


@router.post("/corpus/{corpus_id}/generate_cases", response_model=dict)
def generate_cases(corpus_id: int) -> dict:
    return service.generate_cases_for_corpus(corpus_id=corpus_id)


@router.post("/corpus/{corpus_id}/quality_check", response_model=dict)
def quality_check(corpus_id: int) -> dict:
    return service.quality_check_corpus(corpus_id=corpus_id)


@router.post("/corpus/{corpus_id}/export", response_model=dict)
def export_corpus(corpus_id: int, format: str = Form("jsonl")) -> dict:
    return service.export_corpus(corpus_id=corpus_id, format=format)


@router.post("/retrieval/query", response_model=QueryResponse)
def query_retrieval(request: QueryRequest) -> QueryResponse:
    try:
        return service.query_retrieval(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
