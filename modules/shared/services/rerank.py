from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Tuple

# 本地模型目录：由宿主机 ./models 挂载进容器（使用者手动下载 BGE 模型）。
# 优先从本地目录加载，避免运行时联网依赖 HuggingFace / hf-mirror。
_RERANKER_MODEL_ID = "BAAI/bge-reranker-v2-m3"
_RERANKER_LOCAL_DIR = os.path.join(
    os.environ.get("LOCAL_MODELS_DIR", "/app/models"), "bge-reranker-v2-m3"
)


@lru_cache(maxsize=1)
def _get_reranker():
    from sentence_transformers import CrossEncoder

    # 优先加载本地挂载目录；目录不存在时回退到 HuggingFace Hub 在线下载
    if os.path.isdir(_RERANKER_LOCAL_DIR):
        return CrossEncoder(_RERANKER_LOCAL_DIR)
    # bge-reranker-v2-m3 为 CrossEncoder 格式，输出相关性 logits（越大越相关）
    return CrossEncoder(_RERANKER_MODEL_ID)


class RerankService:
    def rerank(
        self, query: str, documents: List[str], top_k: int | None = None
    ) -> List[Tuple[int, float]]:
        """对 (query, doc) 候选对重排，返回 (原始下标, 分数) 列表，按分数降序。"""
        if not documents:
            return []
        reranker = _get_reranker()
        pairs = [(query, doc) for doc in documents]
        scores = reranker.predict(pairs, show_progress_bar=False)
        ranked = sorted(enumerate(scores), key=lambda item: float(item[1]), reverse=True)
        if top_k is not None:
            ranked = ranked[:top_k]
        return [(idx, float(score)) for idx, score in ranked]
