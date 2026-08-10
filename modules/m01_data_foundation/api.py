from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from modules.m01_data_foundation.schemas import (
    BlockOut,
    DocumentOut,
    DocumentUploadResponse,
    JobOut,
    ReuploadResponse,
)
from modules.m01_data_foundation.services.pipeline import PipelineService

documents_router = APIRouter(prefix="/api/documents", tags=["documents"])
jobs_router = APIRouter(prefix="/api/jobs", tags=["jobs"])

pipeline_service = PipelineService()

# 单用户「我的文件库」：仅有两个受保护系统目录，文档必须归属其一，不可删除/移动
SYSTEM_FOLDERS = {
    "基础问题输入文档": "basic",
    "仅泛化输入文档": "gen",
}


# ----------------------------------------------------------------------
# 文档接入
# ----------------------------------------------------------------------
@documents_router.post("/upload", response_model=DocumentUploadResponse)
def upload_document(
    upload_user: str | None = Form(None),
    document_version: str | None = Form(None),
    folder_path: str | None = Form(None),
    purpose: str | None = Form(None),
    file: UploadFile = File(...),
):
    content = file.file.read()
    # 文档必须归属两个受保护系统目录之一，未指定时默认「基础问题输入文档」
    if purpose is None or purpose not in SYSTEM_FOLDERS.values():
        purpose = "basic"
    # folder_path 若提供（上传保留目录结构），必须以受保护系统目录名为根
    if folder_path:
        root = folder_path.split("/")[0]
        if root not in SYSTEM_FOLDERS:
            raise HTTPException(
                status_code=400,
                detail=f"folder_path 必须以受保护系统目录之一为根：{', '.join(SYSTEM_FOLDERS.keys())}",
            )
        # folder_path 根部已隐含用途，二者应一致
        purpose = SYSTEM_FOLDERS[root]
    try:
        result = pipeline_service.upload_document(
            minio_path="",  # 由 pipeline 内部存储后回填路径
            file_name=file.filename or "upload.bin",
            file_type=file.filename or "",
            content=content,
            upload_user=upload_user,
            folder_path=folder_path,
            purpose=purpose,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DocumentUploadResponse(**result)


@documents_router.patch("/{document_id}/move")
def move_document(
    document_id: int,
    folder_path: str | None = Form(None),
    purpose: str | None = Form(None),
):
    """移动文档到目标目录（持久化 folder_path），并据所属子树标记业务用途。

    文档只能在两个受保护系统目录（基础问题输入文档 / 仅泛化输入文档）之内移动，
    允许在系统目录内部的任意子层级目录之间拖动；禁止游离到系统目录之外，
    也禁止把文件落到名为系统目录但非受保护根的子路径。
    """
    document = pipeline_service.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    # 文档只允许归属两个受保护系统目录（基础问题输入文档 / 仅泛化输入文档）之一，
    # 禁止游离到系统目录之外或落到同名非系统目录。
    if purpose is not None and purpose not in SYSTEM_FOLDERS.values():
        raise HTTPException(
            status_code=400,
            detail=f"purpose 必须为系统目录用途之一：{', '.join(set(SYSTEM_FOLDERS.values()))}",
        )
    # folder_path 若提供，必须以受保护系统目录名为根（如「基础问题输入文档/子A/子B」），
    # 子层级用「/」分隔；不允许落到系统目录之外的任意位置。
    if folder_path:
        root = folder_path.split("/")[0]
        if root not in SYSTEM_FOLDERS:
            raise HTTPException(
                status_code=400,
                detail=f"folder_path 必须以受保护系统目录之一为根：{', '.join(SYSTEM_FOLDERS.keys())}",
            )
        # 若同时显式指定 purpose，其与 folder_path 根部必须一致
        if purpose is not None and SYSTEM_FOLDERS[root] != purpose:
            raise HTTPException(
                status_code=400,
                detail="folder_path 根部所属系统目录与 purpose 不一致",
            )
    pipeline_service.database.update_document(
        document_id, folder_path=folder_path, purpose=purpose
    )
    return {"document_id": document_id, "folder_path": folder_path, "purpose": purpose}


@documents_router.get("", response_model=list[DocumentOut])
def list_documents():
    return pipeline_service.list_documents()


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


@documents_router.delete("/{document_id}")
def delete_document(document_id: int):
    """物理删除文档：块 + 知识点 + 落盘文件 + 向量索引。"""
    document = pipeline_service.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    try:
        pipeline_service.delete_document(document_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"删除失败：{exc}") from exc
    return {"document_id": document_id, "deleted": True}


# ----------------------------------------------------------------------
# 任务进度
# ----------------------------------------------------------------------
@jobs_router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int):
    job = pipeline_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
