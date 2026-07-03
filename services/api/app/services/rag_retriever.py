"""RAG 检索服务：基于 ChromaDB 的医学知识向量检索，支持 MMR 多样性排序和 Cross-Encoder 精排。

嵌入模型：BAAI/bge-large-zh-v1.5（1024维，中文检索 SOTA，支持 instruction 前缀）
重排模型：BAAI/bge-reranker-v2-m3（Cross-Encoder，可选开启）
"""
from __future__ import annotations

import os
import logging
from functools import lru_cache

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "chroma_db")
COLLECTION_NAME = "medical_knowledge"

# 中文嵌入模型名称（从配置读取）
CHINESE_EMBEDDING_MODEL = settings.RAG_EMBEDDING_MODEL


class ChineseEmbeddingFunction(EmbeddingFunction):
    """使用 sentence-transformers 的中文嵌入函数。

    bge 系列模型支持 instruction 前缀：查询时加前缀提升检索精度，
    文档编码时不加前缀。对于非 bge 模型，前缀为空，行为不变。
    """

    # bge 模型推荐的查询前缀
    _BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："

    def __init__(self, model_name: str = CHINESE_EMBEDDING_MODEL):
        self._model_name = model_name
        self._model = None
        self._is_bge = "bge" in model_name.lower()

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"加载中文嵌入模型: {self._model_name}")
            self._model = SentenceTransformer(self._model_name)
            logger.info("中文嵌入模型加载完成")
        return self._model

    def __call__(self, input: Documents) -> Embeddings:
        """ChromaDB 存入时调用，使用文档模式（不加前缀）。"""
        model = self._load_model()
        embeddings = model.encode(input, normalize_embeddings=True)
        return embeddings.tolist()

    def encode_query(self, query: str) -> list[float]:
        """查询时调用，bge 模型自动加 instruction 前缀。"""
        model = self._load_model()
        text = self._BGE_QUERY_PREFIX + query if self._is_bge else query
        embedding = model.encode([text], normalize_embeddings=True)
        return embedding[0].tolist()


# 全局嵌入函数实例（懒加载）
_embedding_fn: ChineseEmbeddingFunction | None = None


def _get_embedding_function() -> ChineseEmbeddingFunction:
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = ChineseEmbeddingFunction()
    return _embedding_fn


class CrossEncoderReranker:
    """Cross-Encoder 重排器：将 query 和 doc 拼接后共同编码，计算精确相关性分数。"""

    def __init__(self, model_name: str):
        self._model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            logger.info(f"加载 Cross-Encoder 重排模型: {self._model_name}")
            self._model = CrossEncoder(self._model_name)
            logger.info("Cross-Encoder 重排模型加载完成")
        return self._model

    def rerank(self, query: str, docs: list[str], top_k: int = 3) -> list[tuple[int, float]]:
        """对候选文档重排，返回 [(original_index, score), ...] 按分数降序。"""
        if not docs:
            return []
        model = self._load_model()
        pairs = [(query, doc) for doc in docs]
        scores = model.predict(pairs)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]


_reranker: CrossEncoderReranker | None = None


def _get_reranker() -> CrossEncoderReranker | None:
    global _reranker
    if not settings.RAG_RERANKER_ENABLED:
        return None
    if _reranker is None:
        _reranker = CrossEncoderReranker(settings.RAG_RERANKER_MODEL)
    return _reranker


def _get_client() -> chromadb.ClientAPI:
    os.makedirs(CHROMA_DIR, exist_ok=True)
    return chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


@lru_cache
def _get_collection() -> chromadb.Collection:
    client = _get_client()
    embedding_fn = _get_embedding_function()
    try:
        return client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
            embedding_function=embedding_fn,
        )
    except (ValueError, Exception):
        # Embedding function conflict — collection was created with a different function
        # Return collection without embedding function; queries will use query_embeddings directly
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


def search_documents(
    query: str,
    top_k: int = 3,
    score_threshold: float | None = None,
    use_mmr: bool | None = None,
) -> list[dict]:
    """检索与 query 最相关的医学知识片段，返回结构化结果。重点供 API 使用。

    Args:
        query: 查询文本
        top_k: 返回的最大文档数
        score_threshold: 最低相似度阈值（0-1），低于此值的文档被过滤。默认从 settings 读取。
        use_mmr: 是否使用 MMR 重排。默认从 settings 读取。
    """
    collection = _get_collection()
    if collection.count() == 0:
        return []

    if score_threshold is None:
        score_threshold = settings.RAG_SCORE_THRESHOLD
    if use_mmr is None:
        use_mmr = settings.RAG_USE_MMR

    n_results = min(top_k * 3, collection.count())  # fetch more for MMR/filtering

    # Use query_embeddings to bypass collection's embedding function and avoid dimension mismatch
    embedding_fn = _get_embedding_function()
    query_embedding = embedding_fn.encode_query(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances", "embeddings"],
    )

    if not results or not results["documents"] or not results["documents"][0]:
        return []

    docs = results["documents"][0]
    metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)
    distances = results["distances"][0] if results["distances"] else [0.0] * len(docs)
    raw_embeddings = results.get("embeddings")
    embeddings = raw_embeddings[0] if raw_embeddings is not None and len(raw_embeddings) > 0 else None

    # Filter by score threshold (ChromaDB cosine distance: lower = more similar)
    max_distance = _cosine_similarity_to_distance(score_threshold)
    filtered = [
        (i, doc, meta, dist)
        for i, (doc, meta, dist) in enumerate(zip(docs, metadatas, distances))
        if dist <= max_distance
    ]

    if not filtered:
        return []

    # MMR re-ranking if enabled and we have embeddings
    if use_mmr and embeddings is not None and len(embeddings) > 0 and len(filtered) > top_k:
        indices = list(range(len(filtered)))
        doc_embeddings = [embeddings[filtered[i][0]] for i in indices]

        # 使用 encode_query 获取查询向量（bge 模型会加 instruction 前缀）
        embedding_fn = _get_embedding_function()
        query_embedding = embedding_fn.encode_query(query)

        mmr_indices = _mmr_rerank(
            query_embedding, doc_embeddings, indices,
            lambda_param=0.5, top_k=top_k,
        )
        filtered = [filtered[i] for i in mmr_indices]
    else:
        filtered = filtered[:top_k]

    # Cross-Encoder 精排（在 MMR 之后，进一步提升排序质量）
    reranker = _get_reranker()
    if reranker and len(filtered) > 1:
        docs_for_rerank = [doc for _, doc, _, _ in filtered]
        reranked = reranker.rerank(query, docs_for_rerank, top_k=settings.RAG_RERANKER_TOP_K)
        filtered = [filtered[i] for i, _ in reranked]

    return [
        {
            "content": doc,
            "metadata": meta or {},
            "score": round(max(0.0, min(1.0, 1.0 - float(dist))), 3),
        }
        for _, doc, meta, dist in filtered
    ]


def retrieve(
    query: str,
    top_k: int = 3,
    score_threshold: float | None = None,
    use_mmr: bool | None = None,
) -> str:
    """检索知识并格式化为适合注入 LLM 上下文的文本。"""
    results = search_documents(
        query,
        top_k=top_k,
        score_threshold=score_threshold,
        use_mmr=use_mmr,
    )

    lines = []
    for item in results:
        doc = item["content"]
        meta = item["metadata"]
        category = meta.get("category", "医学知识")
        source = meta.get("source", "")
        similarity = item["score"]
        prefix = f"[{category}]"
        if source:
            prefix += f" ({source})"
        lines.append(f"{prefix} (相似度:{similarity}) {doc}")

    return "\n---\n".join(lines)


def retrieve_with_images(
    query: str,
    top_k: int = 3,
) -> str:
    """检索文本及已完成 OCR/标题索引的图片知识。"""
    return retrieve(query, top_k=top_k)


def add_documents(
    documents: list[str],
    metadatas: list[dict] | None = None,
    ids: list[str] | None = None,
) -> int:
    """添加文档到知识库。返回添加数量。自动分批处理，避免超过 ChromaDB 批量上限。"""
    import hashlib

    collection = _get_collection()
    if not documents:
        return 0

    if ids is None:
        # 使用索引+内容哈希确保全局唯一
        ids = []
        seen: set[str] = set()
        for i, doc in enumerate(documents):
            meta = metadatas[i] if metadatas and i < len(metadatas) else {}
            chunk_idx = meta.get("chunk_index", 0)
            # 包含索引 i 保证唯一
            raw = f"{i}:{chunk_idx}:{doc[:100]}"
            h = hashlib.md5(raw.encode()).hexdigest()
            # 处理极端碰撞
            while h in seen:
                raw = f"{raw}:dup{i}"
                h = hashlib.md5(raw.encode()).hexdigest()
            seen.add(h)
            ids.append(h)
    if metadatas is None:
        metadatas = [{}] * len(documents)

    # ChromaDB 单次批量上限约 5461，分批添加
    MAX_BATCH = 5000
    total = len(documents)
    for start in range(0, total, MAX_BATCH):
        end = min(start + MAX_BATCH, total)
        batch_documents = documents[start:end]
        # Always provide embeddings explicitly. This keeps writes consistent even
        # when an existing Chroma collection cannot reattach our custom function.
        batch_embeddings = _get_embedding_function()(batch_documents)
        collection.add(
            documents=batch_documents,
            metadatas=metadatas[start:end],
            ids=ids[start:end],
            embeddings=batch_embeddings,
        )

    return total


def delete_documents_by_metadata(document_id: str) -> None:
    """删除指定知识库文档对应的全部向量片段。"""
    collection = _get_collection()
    collection.delete(where={"document_id": document_id})


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
