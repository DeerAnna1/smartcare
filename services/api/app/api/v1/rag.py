"""RAG 医学知识库 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps.auth import get_current_user_required
from app.models.models import User
from app.services.rag_retriever import retrieve, get_stats
from app.services.rag_loader import load_knowledge

router = APIRouter(prefix="/rag", tags=["RAG 知识库"])


class LoadResponse(BaseModel):
    loaded: int
    categories: list[str]


class SearchItem(BaseModel):
    content: str
    metadata: dict


@router.post("/load", response_model=LoadResponse)
async def load_medical_knowledge(
    user: User = Depends(get_current_user_required),
):
    """加载内置医学知识到 ChromaDB 向量库。"""
    result = load_knowledge()
    return LoadResponse(**result)


@router.get("/search")
async def search_knowledge(
    q: str = Query(..., description="检索关键词"),
    top_k: int = Query(3, ge=1, le=10),
    user: User = Depends(get_current_user_required),
):
    """测试 RAG 检索（开发调试用）。"""
    result = retrieve(q, top_k=top_k)
    return {"query": q, "result": result}


@router.get("/stats")
async def knowledge_stats(
    user: User = Depends(get_current_user_required),
):
    """返回知识库统计信息。"""
    return get_stats()
