from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from modules.m01_data_foundation.services.embedding import EmbeddingService
from modules.m01_data_foundation.services.indexer import FaissIndexService, IndexedItem
from modules.m01_data_foundation.services.parser import DocumentParser
from modules.m01_data_foundation.services.storage import StorageService
from modules.shared.core.config import settings
from modules.shared.services.database import DatabaseService


class PipelineService:
    """m01 数据基础：语料库、文档接入、解析、存储与索引。

    不含 RAG 检索（属消费方）也不含 EIU 出题（属 m02），
    仅负责把原始文档变成「结构化文段 + 向量 + FAISS 索引」这一数据底座。
    """

    def __init__(self) -> None:
        self.database = DatabaseService()
        self.embedding = EmbeddingService()
        self.indexer = FaissIndexService(dimension=512)
        self.parser = DocumentParser()
        self.storage = StorageService()
        self._state_path = settings.state_file
        self._ensure_storage()
        self.load_index()

    # ------------------------------------------------------------------
    # 语料库
    # ------------------------------------------------------------------
    def create_corpus(self, *, name: str, description: str | None = None, domain: str | None = None, created_by: str | None = None) -> int:
        return self.database.save_corpus(name=name, description=description, domain=domain, created_by=created_by)

    def list_corpora(self) -> list[dict]:
        return self.database.list_corpora()

    def get_corpus(self, corpus_id: int) -> dict | None:
        return self.database.get_corpus(corpus_id)

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
        corpus_id: int,
        upload_user: str | None = None,
        document_version: str | None = None,
    ) -> dict:
        # file_type 可能是完整文件名或扩展名，统一从 file_name 取扩展名
        suffix = Path(file_name).suffix.lower() or Path(file_type or "").suffix.lower()
        self._validate_file(suffix, content)

        # 原始文件落盘（MinIO 的本地替代，Demo 用）
        stored = self.storage.save_raw_document(file_name, content)
        minio_path = stored.object_path

        file_hash = hashlib.sha256(content).hexdigest()
        existing = self.database.find_by_hash(file_hash, corpus_id=corpus_id)
        if existing is not None:
            return {"document_id": existing, "duplicate": True, "blocks": 0}

        document_id = self.database.save_document(
            corpus_id=corpus_id,
            file_name=file_name,
            file_type=suffix,
            file_size=len(content),
            file_hash=file_hash,
            minio_path=minio_path,
            upload_user=upload_user,
            document_version=document_version,
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
            self.indexer.add(self._to_indexed(indexed, block_ids, document_id))
            self.database.update_document(document_id, parse_status="completed")
            self._save_index()
            return {"document_id": document_id, "duplicate": False, "blocks": len(block_ids)}
        except Exception as exc:  # 解析失败：记录状态与错误，不丢文档
            self.database.update_document(document_id, parse_status="failed", parse_error=str(exc))
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
        corpus_id = existing["corpus_id"]
        suffix = (Path(file_name).suffix if file_name else existing["file_type"]).lower()
        self._validate_file(suffix, content)

        new_hash = hashlib.sha256(content).hexdigest()
        job_id = self.database.save_job(corpus_id=corpus_id, document_id=document_id, job_type="doc_update")
        self.database.update_job(job_id, status="running", phase="parsing", progress=10)

        if new_hash == existing["file_hash"]:
            self.database.update_job(job_id, status="completed", phase="unchanged", progress=100, message="内容未变化，无需重算", finished=True)
            return {"job_id": job_id, "document_id": document_id, "changed": False}

        # 覆盖式全量重算（无版本）：旧文档整体作废，新文档走完整接入流程
        self.database.update_document(document_id, status="superseded")
        stored = self.storage.save_raw_document(file_name or existing["file_name"], content)
        result = self.upload_document(
            minio_path=stored.object_path,
            file_name=file_name or existing["file_name"],
            file_type=suffix,
            content=content,
            corpus_id=corpus_id,
            upload_user=upload_user,
        )
        self.database.update_job(
            job_id,
            status="completed",
            phase="done",
            progress=100,
            message=f"已重算，新文档 ID={result['document_id']}",
            finished=True,
        )
        return {"job_id": job_id, "document_id": result["document_id"], "changed": True}

    # ------------------------------------------------------------------
    # 文档 / 块 / 任务 查询
    # ------------------------------------------------------------------
    def get_document(self, document_id: int) -> dict | None:
        return self.database.get_document(document_id)

    def list_documents(self, corpus_id: int | None = None) -> list[dict]:
        return self.database.list_documents(corpus_id)

    def get_document_blocks(self, document_id: int) -> list[dict]:
        return self.database.get_document_blocks(document_id)

    def get_job(self, job_id: int) -> dict | None:
        return self.database.get_job(job_id)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _validate_file(self, suffix: str, content: bytes) -> None:
        if suffix not in settings.allowed_extensions:
            raise ValueError(f"不支持的文件类型 {suffix}，允许: {settings.allowed_extensions}")
        if content is not None and len(content) > settings.max_file_size:
            raise ValueError(f"文件大小 {len(content)} 超过上限 {settings.max_file_size} 字节")

    def embed_blocks(self, blocks: list) -> list[dict]:
        vectors = self.embedding.embed_texts([block.block_text for block in blocks])
        result: list[dict] = []
        for block, vector in zip(blocks, vectors, strict=True):
            # 强制转为普通 list，避免 numpy ndarray 落入 JSON 列导致序列化失败
            vec_list = np.asarray(vector, dtype="float32").tolist()
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
                    "embedding_vector": vec_list,
                }
            )
        return result

    def _to_indexed(self, indexed: list[dict], block_ids: list[int], document_id: int) -> list[IndexedItem]:
        items: list[IndexedItem] = []
        for block_id, block in zip(block_ids, indexed, strict=True):
            items.append(
                IndexedItem(
                    block_id=block_id,
                    document_id=document_id,
                    section_path=block["section_path"],
                    vector=np.asarray(block["embedding_vector"], dtype="float32").tolist(),
                    source_text=block["block_text"],
                )
            )
        return items

    def _ensure_storage(self) -> None:
        for directory in (settings.raw_dir, settings.parsed_dir, settings.index_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def _save_index(self) -> None:
        state = {
            "items": [
                {
                    "block_id": item.block_id,
                    "document_id": item.document_id,
                    "section_path": item.section_path,
                    "vector": np.asarray(item.vector, dtype="float32").tolist(),
                    "source_text": item.source_text,
                }
                for item in self.indexer._items
            ]
        }
        self._state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def load_index(self) -> None:
        if not self._state_path.exists():
            return
        try:
            state = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        items = [
            IndexedItem(
                block_id=entry["block_id"],
                document_id=entry["document_id"],
                section_path=entry["section_path"],
                vector=np.asarray(entry["vector"], dtype="float32"),
                source_text=entry["source_text"],
            )
            for entry in state.get("items", [])
        ]
        if items:
            self.indexer.add(items)
