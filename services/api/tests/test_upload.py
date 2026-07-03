"""上传接口鉴权测试。"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_upload_document_requires_auth(test_client: AsyncClient):
    """测试无 token 访问上传文档返回 401。"""
    resp = await test_client.post("/api/v1/upload/document")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upload_avatar_requires_auth(test_client: AsyncClient):
    """测试无 token 访问上传头像返回 401。"""
    resp = await test_client.post("/api/v1/upload/avatar")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upload_audio_requires_auth(test_client: AsyncClient):
    """测试无 token 访问上传音频返回 401。"""
    resp = await test_client.post("/api/v1/upload/audio")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upload_video_requires_auth(test_client: AsyncClient):
    """测试无 token 访问上传视频返回 401。"""
    resp = await test_client.post("/api/v1/upload/video")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_document_requires_auth(test_client: AsyncClient):
    """测试无 token 访问文档返回 401。"""
    resp = await test_client.get("/api/v1/upload/document/test.pdf")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_video_requires_auth(test_client: AsyncClient):
    """测试无 token 访问视频返回 401。"""
    resp = await test_client.get("/api/v1/upload/video/test.mp4")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_avatar_is_public(test_client: AsyncClient):
    """测试头像访问是公开的（URL 作为 capability token）。"""
    # 即使没有 token，也不应该返回 401，而是 404（文件不存在）
    resp = await test_client.get("/api/v1/upload/avatar/nonexistent/avatar.jpg")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_document_access(test_client: AsyncClient, test_user: dict, test_user_b: dict):
    """测试跨用户文档访问返回 404。"""
    # 用户 A 上传文档
    files = {"file": ("test.txt", b"test content", "text/plain")}
    resp = await test_client.post(
        "/api/v1/upload/document",
        files=files,
        headers=test_user["headers"],
    )
    assert resp.status_code == 200
    filename = resp.json()["filename"]

    # 用户 B 尝试访问用户 A 的文档
    resp = await test_client.get(
        f"/api/v1/upload/document/{filename}",
        headers=test_user_b["headers"],
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_video_access(test_client: AsyncClient, test_user: dict, test_user_b: dict):
    """测试跨用户视频访问返回 404。"""
    # 用户 A 上传视频
    files = {"file": ("test.mp4", b"fake video content", "video/mp4")}
    resp = await test_client.post(
        "/api/v1/upload/video",
        files=files,
        headers=test_user["headers"],
    )
    assert resp.status_code == 200
    filename = resp.json()["filename"]

    # 用户 B 尝试访问用户 A 的视频
    resp = await test_client.get(
        f"/api/v1/upload/video/{filename}",
        headers=test_user_b["headers"],
    )
    assert resp.status_code == 404
