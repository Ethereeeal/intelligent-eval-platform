from __future__ import annotations

from app.schemas.document import QueryRequest, QueryResponse, SearchHit
from app.services.database import DatabaseService
from app.services.indexer import FaissIndexService
from app.utils.embedding import EmbeddingService


class RetrievalService:
    def __init__(self) -> None:
        self.database = DatabaseService()
        self.indexer = FaissIndexService()
        self.embedding = EmbeddingService()

    def query(self, request: QueryRequest) -> QueryResponse:
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
