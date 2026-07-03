"""RAG 管理端点 RBAC 测试。"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from app.models.models import User


@pytest.mark.asyncio
async def test_rag_load_requires_admin(test_client: AsyncClient, test_user: dict, test_db: AsyncSession):
    """测试普通用户调用 /rag/load 返回 403。"""
    resp = await test_client.post(
        "/api/v1/rag/load",
        headers=test_user["headers"],
    )
    assert resp.status_code == 403
    assert "管理员" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_rag_load_documents_requires_admin(test_client: AsyncClient, test_user: dict):
    """测试普通用户调用 /rag/load-documents 返回 403。"""
    resp = await test_client.post(
        "/api/v1/rag/load-documents",
        json={"file_paths": ["/tmp/test.txt"], "category": "test"},
        headers=test_user["headers"],
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_rag_search_requires_auth(test_client: AsyncClient):
    """测试未认证访问 /rag/search 返回 401。"""
    resp = await test_client.get("/api/v1/rag/search?q=test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rag_stats_requires_auth(test_client: AsyncClient):
    """测试未认证访问 /rag/stats 返回 401。"""
    resp = await test_client.get("/api/v1/rag/stats")
    assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skip(reason="需要 RAG 环境初始化，跳过")
async def test_rag_search_works_for_normal_user(test_client: AsyncClient, test_user: dict):
    """测试普通用户可以使用 /rag/search 查询（不返回 403）。"""
    resp = await test_client.get(
        "/api/v1/rag/search?q=感冒",
        headers=test_user["headers"],
    )
    # 可能返回 200 或 500（如果 RAG 未初始化），但不应该是 401 或 403
    assert resp.status_code not in (401, 403)
