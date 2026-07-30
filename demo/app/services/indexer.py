from __future__ import annotations

from dataclasses import dataclass
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
    metadata: dict[str, Any]


class FaissIndexService:
    def __init__(self, dimension: int = 3) -> None:
        self.dimension = dimension
        self._index = faiss.IndexFlatIP(dimension) if faiss is not None else None
        self._items: list[IndexedItem] = []

    def add(self, items: list[IndexedItem]) -> None:
        if not items:
            return
        vectors = np.asarray([item.vector for item in items], dtype="float32")
        if self._index is not None:
            self._index.add(vectors)
        self._items.extend(items)

    def search(self, vector: list[float], top_k: int = 3) -> list[dict[str, Any]]:
        if not self._items:
            return []
        if self._index is None:
            scored = [self._dot(vector, item.vector) for item in self._items]
            ranked = sorted(zip(self._items, scored), key=lambda pair: pair[1], reverse=True)[:top_k]
            return [
                {"block_id": item.block_id, "score": float(score), "metadata": item.metadata}
                for item, score in ranked
            ]
        query = np.asarray([vector], dtype="float32")
        scores, indices = self._index.search(query, top_k)
        results: list[dict[str, Any]] = []
        for score, index in zip(scores[0], indices[0]):
            if index < 0 or index >= len(self._items):
                continue
            item = self._items[index]
            results.append({"block_id": item.block_id, "score": float(score), "metadata": item.metadata})
        return results

    def _dot(self, left: list[float], right: list[float]) -> float:
        left_vector = np.asarray(left, dtype="float32")
        right_vector = np.asarray(right, dtype="float32")
        return float(np.dot(left_vector, right_vector))
