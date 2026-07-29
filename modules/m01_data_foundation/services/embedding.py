from __future__ import annotations

from typing import List


class EmbeddingService:
    def embed_texts(self, texts: List[str]) -> list[list[float]]:
        return [[0.0, 1.0, 0.0] for _ in texts]
