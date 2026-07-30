from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any

from app.core.config import settings
from app.schemas.document import DocumentUploadResponse, QueryRequest, QueryResponse, SearchHit
from app.services.database import DatabaseService
from app.services.eiu_service import EiuService
from app.services.export_service import ExportService
from app.services.indexer import FaissIndexService, IndexedItem
from app.services.parser import DocumentParser
from app.services.qa_service import QAService
from app.services.quality_service import QualityService
from app.services.retrieval import RetrievalService
from app.services.storage import StorageService
from app.utils.embedding import EmbeddingService


@dataclass
class DocumentRecord:
    document_id: int
    corpus_id: int
    file_name: str
    file_type: str
    file_hash: str
    status: str
    created_at: str


@dataclass
class BlockRecord:
    block_id: int
    document_id: int
    section_path: str
    block_text: str
    block_type: str


class PipelineService:
    def __init__(self) -> None:
        self._ensure_storage()
        self._state = self._load_state()
        self.storage = StorageService()
        self.database = DatabaseService()
        self.parser = DocumentParser()
        self.embedding = EmbeddingService()
        self.indexer = FaissIndexService()
        self.retrieval = RetrievalService()
        self.eiu_service = EiuService()
        self.qa_service = QAService()
        self.quality_service = QualityService()
        self.export_service = ExportService()
        self.database.create_all()

    def upload_document(self, file_name: str, file_type: str, corpus_id: int, content: bytes) -> DocumentUploadResponse:
        if not file_name.strip():
            raise ValueError("file_name 不能为空")
        if not content:
            raise ValueError("文件内容不能为空")

        file_hash = hashlib.sha256(content).hexdigest()

        existing_id = self.database.find_by_hash(file_hash)
        if existing_id is not None:
            return DocumentUploadResponse(
                document_id=existing_id,
                task_id=existing_id,
                status="duplicate",
                file_name=file_name,
                block_count=len(self._filtered_blocks()),
            )

        safe_name = f"{file_hash}_{file_name}"
        storage_result = self.storage.save_raw_document(file_name=safe_name, content=content)
        raw_path = settings.raw_dir / safe_name

        document_id = self.database.save_document(
            corpus_id=corpus_id,
            file_name=file_name,
            file_type=file_type,
            file_hash=file_hash,
            storage_path=storage_result.object_path,
        )

        parsed_blocks = self.parser.parse_file(raw_path)
        block_payloads = [
            {
                "section_path": parsed_block.section_path,
                "block_type": parsed_block.block_type,
                "block_text": parsed_block.block_text,
            }
            for parsed_block in parsed_blocks
        ]
        block_texts = [item["block_text"] for item in block_payloads]
        vectors = self.embedding.embed_texts(block_texts)
        indexed_items: list[IndexedItem] = []
        for payload, vector in zip(block_payloads, vectors):
            payload["embedding_vector"] = vector
            indexed_items.append(
                IndexedItem(
                    block_id=0,
                    vector=vector,
                    metadata={"section_path": payload["section_path"], "block_text": payload["block_text"], "document_id": document_id},
                )
            )

        block_ids = self.database.save_blocks(document_id=document_id, blocks=block_payloads)
        for index, block_id in enumerate(block_ids):
            indexed_items[index].block_id = block_id
        self.indexer.add(indexed_items)

        document_record = DocumentRecord(
            document_id=document_id,
            corpus_id=corpus_id,
            file_name=file_name,
            file_type=file_type,
            file_hash=file_hash,
            status="uploaded",
            created_at=datetime.utcnow().isoformat(),
        )
        self._state["documents"].append(document_record.__dict__)
        for payload, block_id in zip(block_payloads, block_ids):
            block_record = BlockRecord(
                block_id=block_id,
                document_id=document_id,
                section_path=payload["section_path"],
                block_text=payload["block_text"],
                block_type=payload["block_type"],
            )
            self._state["blocks"].append(block_record.__dict__)

        self._state["storage"] = {"object_path": storage_result.object_path, "etag": storage_result.etag}
        self._save_state()

        return DocumentUploadResponse(
            document_id=document_id,
            task_id=document_id,
            status="uploaded",
            file_name=file_name,
            block_count=len(block_ids),
        )

    def query_retrieval(self, request: QueryRequest) -> QueryResponse:
        if not request.question.strip():
            raise ValueError("question 不能为空")

        blocks = self.database.list_blocks(corpus_id=request.corpus_id)
        query_vector = self.embedding.embed_texts([request.question])[0]
        ranked = self.indexer.search(query_vector, top_k=request.top_k)
        hit_map = {item["block_id"]: item for item in blocks}
        hits = [
            SearchHit(
                block_id=item["block_id"],
                score=float(item["score"]),
                source_excerpt=hit_map.get(item["block_id"], {}).get("block_text", "")[:200],
                document_id=hit_map.get(item["block_id"], {}).get("document_id", 0),
                section_path=hit_map.get(item["block_id"], {}).get("section_path"),
            )
            for item in ranked
        ]
        answer = hits[0].source_excerpt if hits else "未检索到足够相关的证据。"
        return QueryResponse(
            question=request.question,
            corpus_id=request.corpus_id,
            hits=hits,
            answer=answer,
            debug={"total_blocks": len(blocks), "top_k": request.top_k, "index_size": len(ranked)},
        )

    def create_corpus(self, name: str, description: str | None = None, domain: str | None = None) -> dict[str, Any]:
        corpus_id = self.database.save_corpus(name=name, description=description, domain=domain)
        return {"corpus_id": corpus_id, "name": name, "description": description, "domain": domain}

    def list_corpora(self) -> list[dict[str, Any]]:
        return self.database.list_corpora()

    def extract_eius_for_document(self, document_id: int, corpus_id: int) -> dict[str, Any]:
        extracted = self.eiu_service.extract_eius(document_id=document_id)
        return {"document_id": document_id, "corpus_id": corpus_id, "extracted_eius": len(extracted)}

    def generate_cases_for_corpus(self, corpus_id: int) -> dict[str, Any]:
        cases = self.qa_service.generate_cases_for_corpus(corpus_id=corpus_id)
        return {"corpus_id": corpus_id, "generated_cases": len(cases)}

    def quality_check_corpus(self, corpus_id: int) -> dict[str, Any]:
        results = self.quality_service.run_quality_check(corpus_id=corpus_id)
        return {"corpus_id": corpus_id, "results": results}

    def export_corpus(self, corpus_id: int, format: str = "jsonl") -> dict[str, Any]:
        path = self.export_service.export_corpus(corpus_id=corpus_id, format=format)
        return {"corpus_id": corpus_id, "export_path": path}

    def _filtered_blocks(self, corpus_id: int | None = None) -> list[dict[str, Any]]:
        document_by_id = {item["document_id"]: item for item in self._state["documents"]}
        blocks: list[dict[str, Any]] = []
        for block in self._state["blocks"]:
            document = document_by_id.get(block["document_id"])
            if document is None:
                continue
            if corpus_id is not None and document["corpus_id"] != corpus_id:
                continue
            blocks.append(block)
        return blocks

    def _ensure_storage(self) -> None:
        settings.storage_root.mkdir(parents=True, exist_ok=True)
        settings.raw_dir.mkdir(parents=True, exist_ok=True)
        settings.parsed_dir.mkdir(parents=True, exist_ok=True)
        settings.index_dir.mkdir(parents=True, exist_ok=True)
        if not settings.state_file.exists():
            settings.state_file.write_text(json.dumps({"documents": [], "blocks": [], "storage": {}}, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_state(self) -> dict[str, Any]:
        if not settings.state_file.exists():
            return {"documents": [], "blocks": [], "storage": {}}
        return json.loads(settings.state_file.read_text(encoding="utf-8"))

    def _save_state(self) -> None:
        settings.state_file.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
