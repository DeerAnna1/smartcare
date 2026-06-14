"""RAG 医学知识库 API。"""
from __future__ import annotations

import asyncio
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps.auth import get_current_user_required
from app.models.models import User
from app.services.rag_retriever import retrieve, get_stats
from app.services.rag_loader import load_knowledge, load_documents_from_files

router = APIRouter(prefix="/rag", tags=["RAG 知识库"])


class LoadResponse(BaseModel):
    loaded: int
    categories: dict
    source: str = ""
    total_records: int = 0
    skipped: int = 0


class DocumentLoadRequest(BaseModel):
    file_paths: list[str]
    category: str = "医学文献"


class DocumentLoadResponse(BaseModel):
    loaded: int
    files: list[str]


class SearchItem(BaseModel):
    content: str
    metadata: dict


@router.post("/load", response_model=LoadResponse)
async def load_medical_knowledge(
    user: User = Depends(get_current_user_required),
):
    """加载内置医学知识到 ChromaDB 向量库。"""
    result = await asyncio.to_thread(load_knowledge)
    return LoadResponse(**result)


@router.post("/load-documents", response_model=DocumentLoadResponse)
async def load_documents(
    body: DocumentLoadRequest,
    user: User = Depends(get_current_user_required),
):
    """从文件列表加载文档到知识库（支持文本切分）。"""
    result = load_documents_from_files(body.file_paths, body.category)
    return DocumentLoadResponse(**result)


@router.get("/search")
async def search_knowledge(
    q: str = Query(..., description="检索关键词"),
    top_k: int = Query(3, ge=1, le=10),
    score_threshold: float = Query(0.35, ge=0.0, le=1.0, description="最低相似度阈值"),
    use_mmr: bool = Query(True, description="是否使用 MMR 重排"),
    user: User = Depends(get_current_user_required),
):
    """测试 RAG 检索（开发调试用）。"""
    result = retrieve(q, top_k=top_k, score_threshold=score_threshold, use_mmr=use_mmr)
    return {"query": q, "result": result, "params": {"top_k": top_k, "score_threshold": score_threshold, "use_mmr": use_mmr}}


@router.get("/stats")
async def knowledge_stats(
    user: User = Depends(get_current_user_required),
):
    """返回知识库统计信息。"""
    return get_stats()
