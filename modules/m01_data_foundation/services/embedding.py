from __future__ import annotations

import os
from functools import lru_cache
from typing import List

# BGE 官方中文检索查询前缀：检索侧需拼接，文档侧直接 encode
_QUERY_PREFIX = "为这个句子生成表示以用于检索："

# 本地模型目录：由宿主机 ./models 挂载进容器（使用者手动下载 BGE 模型）。
# 优先从本地目录加载，避免运行时联网依赖 HuggingFace / hf-mirror。
_EMBEDDING_MODEL_ID = "BAAI/bge-small-zh-v1.5"
_EMBEDDING_LOCAL_DIR = os.path.join(
    os.environ.get("LOCAL_MODELS_DIR", "/app/models"), "bge-small-zh-v1.5"
)


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer

    # 优先加载本地挂载目录；目录不存在时回退到 HuggingFace Hub 在线下载
    if os.path.isdir(_EMBEDDING_LOCAL_DIR):
        return SentenceTransformer(_EMBEDDING_LOCAL_DIR)
    return SentenceTransformer(_EMBEDDING_MODEL_ID)


class EmbeddingService:
    def embed_texts(self, texts: List[str], is_query: bool = False) -> list[list[float]]:
        if is_query:
            texts = [f"{_QUERY_PREFIX}{text}" for text in texts]
        model = _get_model()
        # normalize_embeddings=True + IndexFlatIP(内积) = 余弦相似度
        vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return vectors.astype("float32").tolist()
