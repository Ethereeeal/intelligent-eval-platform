from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

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
folders_router = APIRouter(prefix="/api/folders", tags=["folders"])

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
    # 文档统一归属「文档库」根下的任意目录；未指定用途时默认基础问题输入（basic）
    if purpose is None or purpose not in SYSTEM_FOLDERS.values():
        purpose = "basic"
    # folder_path：相对「文档库」根目录的子路径（如「子A/子B」），允许任意层级，不强制以系统目录为根
    if folder_path:
        folder_path = folder_path.strip("/")
    try:
        # 目标目录持久化：确保路径上的文件夹在 folder 表中有记录（空文件夹刷新后仍保留）
        pipeline_service.database.ensure_folder_path(upload_user or "web", folder_path)
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

    文档统一归属「文档库」根下的任意目录，不再区分基础/泛化系统目录；
    purpose 仅作业务用途标记，缺省或非系统值时回退为 basic（与上传接口一致）。
    """
    document = pipeline_service.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    # 目录模型已统一为「文档库 + 用户自建文件夹」，不再强绑定系统目录用途。
    # purpose 仅记录业务用途，非系统值时回退为 basic（与 upload_document 处理一致）。
    if purpose is None or purpose not in SYSTEM_FOLDERS.values():
        purpose = "basic"
    # folder_path：相对「文档库」根目录的子路径（如「子A/子B」），允许任意层级
    # 移到「文档库」根：FastAPI 会把空串表单解析为 None，而 update_document 以 None
    # 表示「不更新」，因此这里显式规范化为空串，确保根目录（folder_path=''）能写入数据库
    if folder_path is None:
        folder_path = ""
    elif folder_path:
        folder_path = folder_path.strip("/")
    # 目标目录持久化：确保目标文件夹在 folder 表中有记录
    pipeline_service.database.ensure_folder_path(
        document.get("upload_user") or "web", folder_path
    )
    pipeline_service.database.update_document(
        document_id, folder_path=folder_path, purpose=purpose
    )
    return {"document_id": document_id, "folder_path": folder_path, "purpose": purpose}


@documents_router.patch("/{document_id}/rename")
def rename_document(document_id: int, new_name: str = Form(...)):
    """重命名文档（仅更新显示名 file_name，不影响落盘文件与问答对数据）。

    与文件夹重命名一致：只改名字，不迁移存储；已生成的问答对（generated_case）
    独立于 document 表，不受重命名影响。
    """
    document = pipeline_service.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    new_name = (new_name or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="新文件名不能为空")
    pipeline_service.database.update_document(document_id, file_name=new_name)
    return {"document_id": document_id, "file_name": new_name}


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


# ----------------------------------------------------------------------
# 文件夹（文档库目录）：用户自建文件夹持久化
# 路径均为相对「文档库」根的子路径（如「子A/子B」），空串=文档库根
# ----------------------------------------------------------------------
@folders_router.get("")
def list_folders(owner: str | None = Query(None)):
    """返回当前文档库的全部文件夹（含空文件夹），前端据此重建目录树。"""
    return pipeline_service.database.list_folders(owner=owner)


@folders_router.post("")
def create_folder(
    owner: str = Form("web"),
    name: str = Form(...),
    parent_path: str | None = Form(None),
):
    """在 parent_path（相对文档库根，空=根下）新建文件夹。"""
    try:
        return pipeline_service.database.create_folder(
            owner=owner, name=name, parent_path=parent_path or ""
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@folders_router.patch("/move")
def move_folder(
    owner: str = Form("web"),
    from_path: str = Form(...),
    to_path: str = Form(...),
):
    """移动/重命名文件夹：from_path（旧相对路径）→ to_path（新完整路径）。

    同目录下改名（父路径相同）、拖到其他目录（父路径不同）均支持；
    文件夹下文档的 folder_path 前缀由后端一并重写。
    """
    try:
        return pipeline_service.database.rename_folder(
            owner=owner, from_path=from_path, to_path=to_path
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@folders_router.delete("")
def delete_folder(path: str = Query(...), owner: str | None = Query(None)):
    """删除文件夹（递归子孙），其下文档自动上移到父目录（不丢文档）。"""
    try:
        return pipeline_service.database.delete_folder(owner=owner, path=path)
    except ValueError as exc:
        status = 404 if "不存在" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
