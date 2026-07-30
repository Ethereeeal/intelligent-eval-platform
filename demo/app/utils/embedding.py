from __future__ import annotations

import hashlib
from typing import List


class EmbeddingService:
    def embed_texts(self, texts: List[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
            vectors.append([
                digest[0] / 255.0,
                digest[1] / 255.0,
                digest[2] / 255.0,
            ])
        return vectors
