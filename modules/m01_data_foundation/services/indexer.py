from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

try:
    import faiss
except ImportError:  # pragma: no cover - optional dependency fallback
    faiss = None


@dataclass
class IndexedItem:
    block_id: int
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    document_id: int = 0
    section_path: str = ""
    source_text: str = ""


class FaissIndexService:
    def __init__(self, dimension: int = 512) -> None:
        self.dimension = dimension
        self._index = faiss.IndexFlatIP(dimension) if faiss is not None else None
        self._items: list[IndexedItem] = []
        # block_id -> 在 _items 中的位置，供"按块查近邻"使用
        self._by_block: dict[int, int] = {}

    def add(self, items: list[IndexedItem]) -> None:
        if not items:
            return
        base = len(self._items)
        vectors = np.asarray([item.vector for item in items], dtype="float32")
        if self._index is not None:
            self._index.add(vectors)
        self._items.extend(items)
        for offset, item in enumerate(items):
            self._by_block[item.block_id] = base + offset

    def remove_by_document(self, document_id: int) -> int:
        """从内存索引中剔除某文档的全部向量条目（覆盖重算后物理删除旧文档用）。

        FAISS 为增量索引不支持单条删除，本项目索引通过 state json 全量持久化，
        故此处仅过滤内存条目，待调用方 _save_index 重写落盘即可真正移除。
        返回被移除的条目数。
        """
        before = len(self._items)
        self._items = [item for item in self._items if item.document_id != document_id]
        removed = before - len(self._items)
        # 重建块位置索引
        self._by_block = {item.block_id: i for i, item in enumerate(self._items)}
        return removed

    def neighbors_of(self, block_id: int, top_k: int = 5) -> list[dict[str, Any]]:
        """跨块出题配对用：返回某个块的 Top-K 语义近邻（排除自身）。

        直接复用同一份全量 FAISS 索引，对每个块做"自检索"。
        """
        pos = self._by_block.get(block_id)
        if pos is None:
            return []
        vector = self._items[pos].vector
        # 多召回 1 个以容纳自身，再剔除
        results = self.search(vector, top_k=top_k + 1)
        return [item for item in results if item["block_id"] != block_id][:top_k]

    def search(self, vector: list[float], top_k: int = 3) -> list[dict[str, Any]]:
        if not self._items:
            return []
        if self._index is None:
            scored = [self._dot(vector, item.vector) for item in self._items]
            ranked = sorted(zip(self._items, scored, strict=True), key=lambda pair: pair[1], reverse=True)[:top_k]
            return [
                {"block_id": item.block_id, "score": float(score), "metadata": item.metadata}
                for item, score in ranked
            ]
        query = np.asarray([vector], dtype="float32")
        scores, indices = self._index.search(query, top_k)
        results: list[dict[str, Any]] = []
        for score, index in zip(scores[0], indices[0], strict=True):
            if index < 0 or index >= len(self._items):
                continue
            item = self._items[index]
            results.append({"block_id": item.block_id, "score": float(score), "metadata": item.metadata})
        return results

    def _dot(self, left: list[float], right: list[float]) -> float:
        left_vector = np.asarray(left, dtype="float32")
        right_vector = np.asarray(right, dtype="float32")
        return float(np.dot(left_vector, right_vector))
