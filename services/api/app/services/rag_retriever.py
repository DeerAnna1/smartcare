"""RAG 检索服务：基于 ChromaDB 的医学知识向量检索。"""
from __future__ import annotations

import os
from functools import lru_cache

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import get_settings

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


def retrieve(query: str, top_k: int = 3) -> str:
    """检索与 query 最相关的医学知识片段，格式化为可注入 prompt 的文本。"""
    collection = _get_collection()
    if collection.count() == 0:
        return ""

    results = collection.query(query_texts=[query], n_results=min(top_k, collection.count()))

    if not results or not results["documents"] or not results["documents"][0]:
        return ""

    docs = results["documents"][0]
    metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)

    lines = []
    for i, (doc, meta) in enumerate(zip(docs, metadatas)):
        category = meta.get("category", "医学知识")
        source = meta.get("source", "")
        prefix = f"[{category}]"
        if source:
            prefix += f" ({source})"
        lines.append(f"{prefix} {doc}")

    return "\n---\n".join(lines)


def add_documents(documents: list[str], metadatas: list[dict] | None = None, ids: list[str] | None = None) -> int:
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
