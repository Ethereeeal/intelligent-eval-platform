"""EIU 向量 FAISS 索引服务。

P0/P1：EIU 为核心实体，其 embedding_vector（BGE，512 维，已归一化）落库后，
本服务从数据库加载全库 EIU 向量构建 FAISS 内积索引（IndexFlatIP，余弦等价），
提供按语句/向量检索 EIU 的能力，用于：
  - EIU 语义去重（m02 抽取）
  - EIU 语义复用 / 未来跨块候选召回（同文档过滤）

FAISS 不可用或库中无向量时优雅降级：无向量返回空列表，不阻断主流程。
"""
from __future__ import annotations

from typing import Any

import numpy as np

try:
    import faiss
except ImportError:  # pragma: no cover - optional dependency fallback
    faiss = None

from modules.shared.services.database import DatabaseService


class EiuFaissIndex:
    """全库 EIU 向量索引（索引内容随调用重建，适合中小规模库）。"""

    def __init__(self, dimension: int = 512) -> None:
        self.dimension = dimension
        self._index = faiss.IndexFlatIP(dimension) if faiss is not None else None
        self._eius: list[dict[str, Any]] = []  # 与索引顺序一致

    # ------------------------------------------------------------------
    # 构建与加载
    # ------------------------------------------------------------------
    def rebuild_from_db(self, db: DatabaseService | None = None) -> int:
        """从数据库重建全库 EIU 向量索引。返回索引的 EIU 数。"""
        self.reset()
        db = db or DatabaseService()
        eius = db.list_eius()
        return self.add_items([e for e in eius if e.get("embedding_vector")])

    def reset(self) -> None:
        """清空索引与条目。"""
        self._eius = []
        if self._index is not None:
            self._index.reset()

    def add_items(self, eius: list[dict[str, Any]]) -> int:
        """增量添加 EIU 条目（带向量）。返回实际添加数。

        兼容未落库条目：抽取去重阶段传入的 item 可能尚无 eiu_id，
        此时用负序号占位，保证检索不因缺 eiu_id 报错。
        """
        vectors = []
        added = 0
        for eiu in eius:
            vec = eiu.get("embedding_vector")
            if not vec or not isinstance(vec, list) or len(vec) == 0:
                continue
            # 容错：首个非空维度确定索引维度；维度不一致则跳过
            if not vectors and self._index is not None and len(vec) != self.dimension:
                self.dimension = len(vec)
                self._index = faiss.IndexFlatIP(self.dimension)
            if len(vec) != self.dimension:
                continue
            # 未落库条目补临时占位 id（负序号）
            if "eiu_id" not in eiu:
                eiu = dict(eiu)
                eiu["eiu_id"] = -len(self._eius) - 1
            vectors.append(vec)
            self._eius.append(eiu)
            added += 1
        if vectors and self._index is not None:
            arr = np.asarray(vectors, dtype="float32")
            self._index.add(arr)
        return added

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    def search_by_text(
        self,
        statement: str,
        *,
        top_k: int = 5,
        document_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """按语句编码后检索最相似 EIU。

        document_id 非空时仅在指定文档内检索（跨块候选/单文档去重用）。
        """
        from modules.m01_data_foundation.services.embedding import EmbeddingService

        try:
            embedder = EmbeddingService()
            (qvec,) = embedder.embed_texts([statement], is_query=True)
        except Exception:
            return []
        return self.search_by_vector(qvec, top_k=top_k, document_id=document_id)

    def search_by_vector(
        self,
        vector: list[float],
        *,
        top_k: int = 5,
        document_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """按向量检索最相似 EIU，返回 [{eiu_id, eiu_type, statement, score, document_id}]。"""
        if not vector or not self._eius:
            return []
        if self._index is not None:
            query = np.asarray([vector], dtype="float32")
            scores, indices = self._index.search(query, top_k + 1)
            results: list[dict[str, Any]] = []
            for score, idx in zip(scores[0], indices[0], strict=True):
                if idx < 0 or idx >= len(self._eius):
                    continue
                eiu = self._eius[idx]
                if document_id is not None and eiu.get("document_id") != document_id:
                    continue
                results.append(
                    {
                        "eiu_id": eiu["eiu_id"],
                        "eiu_type": eiu.get("eiu_type", ""),
                        "statement": eiu.get("statement", ""),
                        "document_id": eiu.get("document_id"),
                        "score": float(score),
                    }
                )
                if len(results) >= top_k:
                    break
            return results
        # FAISS 不可用：线性扫描降级
        scored = []
        for eiu in self._eius:
            if document_id is not None and eiu.get("document_id") != document_id:
                continue
            vec = eiu.get("embedding_vector")
            if not vec:
                continue
            s = float(np.dot(np.asarray(vector, dtype="float32"), np.asarray(vec, dtype="float32")))
            scored.append((s, eiu))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {
                "eiu_id": eiu["eiu_id"],
                "eiu_type": eiu.get("eiu_type", ""),
                "statement": eiu.get("statement", ""),
                "document_id": eiu.get("document_id"),
                "score": round(s, 4),
            }
            for s, eiu in scored[:top_k]
        ]
