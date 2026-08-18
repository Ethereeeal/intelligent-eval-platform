from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from modules.m02_eiu_coverage.services.eiu_extractor import EiuExtractorService
from modules.m05_dataset_lifecycle.services.lifecycle import DatasetLifecycleService
from modules.m01_data_foundation.schemas import (
    BlockOut,
    DocumentOut,
    DocumentUploadResponse,
    JobOut,
    ReuploadResponse,
)
from modules.m01_data_foundation.services.pipeline import PipelineService
from modules.shared.core.config import settings

logger = logging.getLogger(__name__)

documents_router = APIRouter(prefix="/api/documents", tags=["documents"])
jobs_router = APIRouter(prefix="/api/jobs", tags=["jobs"])
folders_router = APIRouter(prefix="/api/folders", tags=["folders"])

pipeline_service = PipelineService()
_reupload_extractor = EiuExtractorService()
_reupload_lifecycle = DatasetLifecycleService()

# 同名覆盖确认凭据（内存态，单进程 Demo 够用；多实例生产需换 Redis 等共享存储）
_CONFIRM_TOKEN_TTL_SECONDS = 600  # 10 分钟
_confirm_tokens: dict[str, dict] = {}

# 单用户「我的文件库」：仅有两个受保护系统目录，文档必须归属其一，不可删除/移动
SYSTEM_FOLDERS = {
    "基础问题输入文档": "basic",
    "仅泛化输入文档": "gen",
}


# ----------------------------------------------------------------------
# 文档接入
# ----------------------------------------------------------------------
def _read_upload_with_limit(file: UploadFile) -> bytes:
    """流式读取上传文件，超过大小上限立即拒绝（避免整文件读入内存后才校验超限）。"""
    limit = settings.max_file_size
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail=f"文件大小超过上限 {limit} 字节")
        chunks.append(chunk)
    return b"".join(chunks)


def _prune_expired_confirm_tokens() -> None:
    """签发新 token 时顺带清理已过期的未消费 token，避免内存累积。"""
    now = time.time()
    expired = [
        token for token, entry in _confirm_tokens.items()
        if now - entry["created_at"] > _CONFIRM_TOKEN_TTL_SECONDS
    ]
    for token in expired:
        _confirm_tokens.pop(token, None)


def _issue_confirm_token(*, document_id: int, folder_path: str | None, file_hash: str) -> str:
    """生成一次性确认凭据：绑定目标文档 + 新文件哈希，防确认时偷换文件。"""
    _prune_expired_confirm_tokens()
    token = secrets.token_hex(16)
    _confirm_tokens[token] = {
        "document_id": document_id,
        "folder_path": folder_path,
        "file_hash": file_hash,
        "created_at": time.time(),
    }
    return token


def _validate_confirm_token(token: str, document_id: int, file_hash: str) -> str | None:
    """校验并消费确认凭据；失败返回原因，成功返回 None（一次性）。"""
    entry = _confirm_tokens.pop(token, None)
    if entry is None:
        return "确认凭据无效或已过期，请重新上传"
    if time.time() - entry["created_at"] > _CONFIRM_TOKEN_TTL_SECONDS:
        return "确认凭据已过期，请重新上传"
    if entry["document_id"] != document_id:
        return "确认目标文档已变化，请重新上传"
    if entry["file_hash"] != file_hash:
        return "确认内容与上传内容不一致，请重新上传"
    return None


@documents_router.post("/precheck")
def precheck_upload(
    folder_path: str | None = Form(None),
    file: UploadFile = File(...),
):
    """上传预检（只读、不落盘）：计算哈希并判定 ok / conflict / duplicate / 弱提示。

    - ok：无冲突，可直接上传；
    - duplicate：内容已存在（全库哈希命中），应跳过；
    - conflict：目标文件夹存在同名且内容不同，需用户确认后带 confirm_token 走 reupload；
    - ok + same_name_elsewhere：其他位置有同名文件（弱提示，不拦截）。
    """
    content = _read_upload_with_limit(file)
    file_name = file.filename or "upload.bin"
    suffix = Path(file_name).suffix.lower()
    if suffix not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 {suffix}，允许: {settings.allowed_extensions}",
        )
    if len(content) > settings.max_file_size:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小 {len(content)} 超过上限 {settings.max_file_size} 字节",
        )

    file_hash = hashlib.sha256(content).hexdigest()
    fp = (folder_path or "").strip("/")
    db = pipeline_service.database

    dup_id = db.find_by_hash(file_hash)
    if dup_id is not None:
        return {"status": "duplicate", "existing_document_id": dup_id}

    same = db.find_document_by_name_in_folder(file_name, fp)
    if same is not None and same["file_hash"] != file_hash:
        token = _issue_confirm_token(
            document_id=same["document_id"],
            folder_path=same.get("folder_path"),
            file_hash=file_hash,
        )
        return {
            "status": "conflict",
            "existing_document_id": same["document_id"],
            "existing_name": same["file_name"],
            "existing_folder": same.get("folder_path") or "文档库",
            "existing_upload_time": same.get("upload_time"),
            "existing_size": same.get("file_size"),
            "confirm_token": token,
        }

    elsewhere = [
        item for item in db.find_documents_by_name(file_name)
        if (item["folder_path"] or "") != fp
    ]
    if elsewhere:
        return {"status": "ok", "same_name_elsewhere": elsewhere}
    return {"status": "ok"}


@documents_router.post("/upload", response_model=DocumentUploadResponse)
def upload_document(
    upload_user: str | None = Form(None),
    document_version: str | None = Form(None),
    folder_path: str | None = Form(None),
    purpose: str | None = Form(None),
    file: UploadFile = File(...),
):
    content = _read_upload_with_limit(file)
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
def reupload_document(
    document_id: int,
    file: UploadFile = File(...),
    confirm_token: str | None = Form(None),
):
    content = _read_upload_with_limit(file)
    if confirm_token:
        file_hash = hashlib.sha256(content).hexdigest()
        token_error = _validate_confirm_token(confirm_token, document_id, file_hash)
        if token_error:
            raise HTTPException(status_code=400, detail=token_error)
    try:
        result = pipeline_service.reupload_document(
            document_id=document_id,
            content=content,
            file_name=file.filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — 未预期错误统一收敛为 500，避免裸异常外泄
        logger.error("文档 %s 重传发生未预期错误: %s", document_id, exc)
        raise HTTPException(status_code=500, detail="重传处理失败，请稍后重试或查看日志") from exc
    if result.get("changed"):
        # 重传闭环编排（异步）：EIU 重抽 → 版本覆盖重建 → 删除旧文档，
        # 全程共用一个 doc_update_job（parsing → eiu_extract → rebuild → done/failed）。
        threading.Thread(
            target=_run_reupload_chain,
            kwargs={
                "job_id": result["job_id"],
                "new_document_id": result["document_id"],
                "old_document_id": result["old_document_id"],
            },
            daemon=True,
        ).start()
    return ReuploadResponse(**result)


def _run_reupload_chain(*, job_id: int, new_document_id: int, old_document_id: int) -> None:
    """重传闭环：EIU 重抽（复用同一 job）→ 评测集版本重建 → 删除旧文档。

    任一环节失败：回滚新文档（块/EIU/落盘文件），保留旧文档，job 置 failed。
    全链路成功后的旧文档清理单独处理：清理失败不触发新文档回滚（新文档已生效）。
    """
    db = pipeline_service.database
    phase = "parsing"
    try:
        # 1) EIU 重抽：不自行完结 job（finalize_job=False），阶段由编排统一收口
        phase = "eiu_extract"
        extract_result = _reupload_extractor.extract_document(
            new_document_id,
            job_id,
            finalize_job=False,
            progress_start=40,
            progress_end=90,
        )
        if extract_result.get("status") == "failed":
            raise RuntimeError(extract_result.get("message") or "EIU 抽取失败")
        db.update_job(
            job_id,
            phase="eiu_extract",
            progress=90,
            message=f"EIU 抽取完成（{extract_result.get('count', 0)} 条），开始版本重建",
        )
        # 2) 评测集版本覆盖式重建（内部将 job 置 done / "已更新完成"）
        phase = "rebuild"
        _reupload_lifecycle.rebuild_on_reupload(
            document_id=new_document_id, job_id=job_id
        )
    except Exception as exc:  # noqa: BLE001 — 编排异常统一收敛为 job failed
        logger.warning("文档重传闭环失败 job=%s new_doc=%s: %s", job_id, new_document_id, exc)
        try:
            pipeline_service.delete_document(new_document_id)
        except Exception as rollback_exc:  # noqa: BLE001
            logger.error("重传失败回滚新文档异常 job=%s: %s", job_id, rollback_exc)
        db.update_job(
            job_id,
            status="failed",
            phase=phase,
            message=f"重传闭环失败（{phase} 阶段），已保留旧文档: {exc}",
            finished=True,
        )
        return
    # 3) 全链路成功，删除旧文档（块 / EIU / 问答对 / 落盘文件）。
    #    清理失败只标记 job，不删除已生效的新文档。
    try:
        pipeline_service.delete_document(old_document_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("重传闭环完成但旧文档清理失败 job=%s old_doc=%s: %s", job_id, old_document_id, exc)
        db.update_job(
            job_id,
            status="failed",
            phase="rebuild",
            message=f"新文档已生效，但旧文档清理失败: {exc}",
            finished=True,
        )


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
