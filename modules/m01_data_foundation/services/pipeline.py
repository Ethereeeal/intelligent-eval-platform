from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from modules.m01_data_foundation.services.embedding import EmbeddingService
from modules.m01_data_foundation.services.parser import DocumentParser
from modules.m01_data_foundation.services.storage import StorageService
from modules.shared.core.config import settings
from modules.shared.services.database import DatabaseService

logger = logging.getLogger(__name__)


class PipelineService:
    """m01 数据基础：语料库、文档接入、解析、存储与索引。

    不含 RAG 检索（属消费方）也不含 EIU 出题（属 m02），
    仅负责把原始文档变成「结构化文段 + 向量 + FAISS 索引」这一数据底座。
    """

    def __init__(self) -> None:
        self.database = DatabaseService()
        self.embedding = EmbeddingService()
        self.parser = DocumentParser()
        self.storage = StorageService()
        self._ensure_storage()

    # ------------------------------------------------------------------
    # 文档接入
    # ------------------------------------------------------------------
    def list_corpora(self) -> list[dict]:
        return self.database.list_documents()

    # ------------------------------------------------------------------
    # 文档接入
    # ------------------------------------------------------------------
    def upload_document(
        self,
        *,
        minio_path: str | None = None,
        file_name: str,
        file_type: str,
        content: bytes,
        upload_user: str | None = None,
        document_version: str | None = None,
        folder_path: str | None = None,
        purpose: str | None = None,
    ) -> dict:
        # file_type 可能是完整文件名或扩展名，统一从 file_name 取扩展名
        suffix = Path(file_name).suffix.lower() or Path(file_type or "").suffix.lower()
        self._validate_file(suffix, content)

        # 原始文件落盘（MinIO 的本地替代，Demo 用）
        stored = self.storage.save_raw_document(file_name, content)
        minio_path = stored.object_path

        file_hash = hashlib.sha256(content).hexdigest()
        existing = self.database.find_by_hash(file_hash)
        if existing is not None:
            return {"document_id": existing, "duplicate": True, "blocks": 0}

        document_id = self.database.save_document(
            file_name=file_name,
            file_type=suffix,
            file_size=len(content),
            file_hash=file_hash,
            minio_path=minio_path,
            upload_user=upload_user,
            document_version=document_version,
            folder_path=folder_path,
            purpose=purpose,
            parse_status="pending",
        )
        try:
            parse_path = Path(minio_path)
            if not parse_path.exists():
                # 兜底：minio_path 解析不到时按 raw_dir 重建绝对路径
                candidate = settings.raw_dir.resolve() / Path(minio_path).name
                if candidate.exists():
                    parse_path = candidate
            blocks = self.parser.parse_document(parse_path, suffix)
            indexed = self.embed_blocks(blocks)
            block_ids = self.database.save_blocks(document_id=document_id, blocks=indexed)
            # P0：块不再构建 FAISS 索引，块向量已废弃，仅保留块作定位分片
            self.database.update_document(document_id, parse_status="completed")
            return {"document_id": document_id, "duplicate": False, "blocks": len(block_ids)}
        except Exception as exc:  # 解析/入库失败：整体回滚，不在库里留下残句，避免重新上传误判
            logger.warning("文档 %s 接入失败，执行回滚清理: %s", document_id, exc)
            try:
                self.database.delete_document(document_id)
                self.storage.delete_raw_document(minio_path)
            except Exception as cleanup_exc:
                logger.error("回滚清理失败 document=%s: %s", document_id, cleanup_exc)
            raise

    def reupload_document(
        self,
        *,
        document_id: int,
        content: bytes,
        file_name: str | None = None,
        upload_user: str | None = None,
    ) -> dict:
        existing = self.database.get_document(document_id)
        if existing is None:
            raise ValueError("document not found")
        suffix = (Path(file_name).suffix if file_name else existing["file_type"]).lower()
        self._validate_file(suffix, content)

        new_hash = hashlib.sha256(content).hexdigest()
        job_id = self.database.save_job(document_id=document_id, job_type="doc_update")
        self.database.update_job(job_id, status="running", phase="parsing", progress=10)

        if new_hash == existing["file_hash"]:
            self.database.update_job(job_id, status="completed", phase="unchanged", progress=100, message="内容未变化，无需重算", finished=True)
            return {"job_id": job_id, "document_id": document_id, "changed": False}

        # 覆盖式全量重算：旧文档物理删除，新内容走完整接入流程重新解析、重新抽取。
        # 文档本身不做版本留痕；问答对的最终版本管理由 m05 的 dataset_version（冻结版本）统一负责。
        old_minio_path = existing.get("minio_path")
        old_document_id = document_id
        stored = self.storage.save_raw_document(file_name or existing["file_name"], content)
        result = self.upload_document(
            minio_path=stored.object_path,
            file_name=file_name or existing["file_name"],
            file_type=suffix,
            content=content,
            upload_user=upload_user,
        )
        new_document_id = result["document_id"]
        # P0：块向量索引已废弃，仅物理删除旧文档（块 + 知识点 + 落盘文件）
        self.database.delete_document(old_document_id)
        self.storage.delete_raw_document(old_minio_path)
        self.database.update_job(
            job_id,
            status="completed",
            phase="done",
            progress=100,
            message=f"已重算，新文档 ID={new_document_id}（旧文档已删除）",
            finished=True,
        )
        return {"job_id": job_id, "document_id": new_document_id, "changed": True}

    # ------------------------------------------------------------------
    # 文档 / 块 / 任务 查询
    # ------------------------------------------------------------------
    def get_document(self, document_id: int) -> dict | None:
        return self.database.get_document(document_id)

    def list_documents(self) -> list[dict]:
        return self.database.list_documents()

    def get_document_blocks(self, document_id: int) -> list[dict]:
        return self.database.get_document_blocks(document_id)

    def get_job(self, job_id: int) -> dict | None:
        return self.database.get_job(job_id)

    def delete_document(self, document_id: int) -> None:
        """彻底删除一个文档：库表清理 + 落盘文件清理。

        与 reupload 的回滚清理逻辑一致，但此处不创建新文档。
        """
        existing = self.database.get_document(document_id)
        if existing is None:
            return
        minio_path = existing.get("minio_path")
        self.database.delete_document(document_id)
        self.storage.delete_raw_document(minio_path)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _validate_file(self, suffix: str, content: bytes) -> None:
        if suffix not in settings.allowed_extensions:
            raise ValueError(f"不支持的文件类型 {suffix}，允许: {settings.allowed_extensions}")
        if content is not None and len(content) > settings.max_file_size:
            raise ValueError(f"文件大小 {len(content)} 超过上限 {settings.max_file_size} 字节")

    def embed_blocks(self, blocks: list) -> list[dict]:
        """将解析出的块转为落库 dict。

        P0 改造：块不再做 BGE 向量化。embedding 只针对 EIU（m02 抽取阶段），
        块仅作为「定位分片」承载原文片段，消除冗余的块向量层。
        embedding_vector 一律置 None，节省存储与上传耗时。
        """
        result: list[dict] = []
        for block in blocks:
            result.append(
                {
                    "section_path": block.section_path,
                    "block_type": block.block_type,
                    "block_text": block.block_text,
                    "parent_index": block.parent_index,
                    "page_no": block.page_no,
                    "start_offset": block.start_offset,
                    "end_offset": block.end_offset,
                    "metadata_json": block.metadata_json,
                    "embedding_vector": None,
                }
            )
        return result

    def _ensure_storage(self) -> None:
        for directory in (settings.raw_dir, settings.parsed_dir):
            directory.mkdir(parents=True, exist_ok=True)
