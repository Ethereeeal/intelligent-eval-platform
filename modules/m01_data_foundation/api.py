from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from modules.m01_data_foundation.schemas import DocumentUploadResponse, QueryRequest, QueryResponse
from modules.m01_data_foundation.services.pipeline import PipelineService

router = APIRouter(prefix="/api")
pipeline_service = PipelineService()


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    corpus_id: int = Form(...),
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    try:
        content = await file.read()
        return pipeline_service.upload_document(
            file_name=file.filename or "uploaded_file",
            file_type=file.content_type or "application/octet-stream",
            corpus_id=corpus_id,
            content=content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/retrieval/query", response_model=QueryResponse)
def query_retrieval(request: QueryRequest) -> QueryResponse:
    try:
        return pipeline_service.query_retrieval(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
