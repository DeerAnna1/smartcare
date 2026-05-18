"""RAG 检索服务：基于 ChromaDB 的医学知识向量检索，支持 MMR 和 score 阈值。"""
from __future__ import annotations

import os
import logging
from functools import lru_cache

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "chroma_db")
COLLECTION_NAME = "medical_knowledge"


def _get_client() -> chromadb.ClientAPI:
    os.makedirs(CHROMA_DIR, exist_ok=True)
    return chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


@lru_cache
def _get_collection() -> chromadb.Collection:
    client = _get_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _cosine_similarity_to_distance(similarity: float) -> float:
    """ChromaDB cosine distance = 1 - cosine_similarity."""
    return 1.0 - similarity


def _mmr_rerank(
    query_embedding: list[float],
    doc_embeddings: list[list[float]],
    doc_indices: list[int],
    lambda_param: float = 0.5,
    top_k: int = 3,
) -> list[int]:
    """Maximal Marginal Relevance re-ranking.

    Balances relevance to the query against diversity among selected docs.
    Returns indices into the original doc_indices list.
    """
    import math

    def _dot(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    def _norm(a: list[float]) -> float:
        return math.sqrt(sum(x * x for x in a))

    def _cosine_sim(a: list[float], b: list[float]) -> float:
        n = _norm(a) * _norm(b)
        if n == 0:
            return 0.0
        return _dot(a, b) / n

    selected: list[int] = []
    remaining = set(range(len(doc_indices)))

    # Pre-compute query similarities
    query_sims = [_cosine_sim(query_embedding, doc_embeddings[i]) for i in range(len(doc_indices))]

    for _ in range(min(top_k, len(doc_indices))):
        best_idx = -1
        best_score = -float("inf")

        for idx in remaining:
            relevance = query_sims[idx]
            # Max similarity to already selected docs
            diversity_penalty = 0.0
            if selected:
                diversity_penalty = max(
                    _cosine_sim(doc_embeddings[idx], doc_embeddings[sel])
                    for sel in selected
                )
            mmr_score = lambda_param * relevance - (1 - lambda_param) * diversity_penalty
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx

        if best_idx >= 0:
            selected.append(best_idx)
            remaining.discard(best_idx)

    return selected


def retrieve(
    query: str,
    top_k: int = 3,
    score_threshold: float | None = None,
    use_mmr: bool | None = None,
) -> str:
    """检索与 query 最相关的医学知识片段。

    Args:
        query: 查询文本
        top_k: 返回的最大文档数
        score_threshold: 最低相似度阈值（0-1），低于此值的文档被过滤。默认从 settings 读取。
        use_mmr: 是否使用 MMR 重排。默认从 settings 读取。
    """
    collection = _get_collection()
    if collection.count() == 0:
        return ""

    if score_threshold is None:
        score_threshold = settings.RAG_SCORE_THRESHOLD
    if use_mmr is None:
        use_mmr = settings.RAG_USE_MMR

    n_results = min(top_k * 3, collection.count())  # fetch more for MMR/filtering

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances", "embeddings"],
    )

    if not results or not results["documents"] or not results["documents"][0]:
        return ""

    docs = results["documents"][0]
    metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)
    distances = results["distances"][0] if results["distances"] else [0.0] * len(docs)
    embeddings = results["embeddings"][0] if results.get("embeddings") else None

    # Filter by score threshold (ChromaDB cosine distance: lower = more similar)
    max_distance = _cosine_similarity_to_distance(score_threshold)
    filtered = [
        (i, doc, meta, dist)
        for i, (doc, meta, dist) in enumerate(zip(docs, metadatas, distances))
        if dist <= max_distance
    ]

    if not filtered:
        return ""

    # MMR re-ranking if enabled and we have embeddings
    if use_mmr and embeddings and len(filtered) > top_k:
        indices = list(range(len(filtered)))
        doc_embeddings = [embeddings[filtered[i][0]] for i in indices]
        query_embedding = collection.query(
            query_texts=[query], n_results=1, include=["embeddings"]
        )["embeddings"][0][0] if embeddings else []

        if query_embedding:
            mmr_indices = _mmr_rerank(
                query_embedding, doc_embeddings, indices,
                lambda_param=0.5, top_k=top_k,
            )
            filtered = [filtered[i] for i in mmr_indices]
        else:
            filtered = filtered[:top_k]
    else:
        filtered = filtered[:top_k]

    lines = []
    for _, doc, meta, dist in filtered:
        category = meta.get("category", "医学知识")
        source = meta.get("source", "")
        similarity = round(1.0 - dist, 3)
        prefix = f"[{category}]"
        if source:
            prefix += f" ({source})"
        lines.append(f"{prefix} (相似度:{similarity}) {doc}")

    return "\n---\n".join(lines)


def add_documents(
    documents: list[str],
    metadatas: list[dict] | None = None,
    ids: list[str] | None = None,
) -> int:
    """添加文档到知识库。返回添加数量。"""
    collection = _get_collection()
    if not documents:
        return 0

    if ids is None:
        import hashlib
        ids = [hashlib.md5(doc.encode()).hexdigest() for doc in documents]
    if metadatas is None:
        metadatas = [{}] * len(documents)

    collection.add(documents=documents, metadatas=metadatas, ids=ids)
    return len(documents)


def get_stats() -> dict:
    """返回知识库统计信息。"""
    collection = _get_collection()
    return {
        "collection": COLLECTION_NAME,
        "document_count": collection.count(),
        "persist_dir": os.path.abspath(CHROMA_DIR),
    }


def clear_collection() -> None:
    """清空知识库（用于重新加载）。"""
    client = _get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    # 重新初始化
    _get_collection.cache_clear()
