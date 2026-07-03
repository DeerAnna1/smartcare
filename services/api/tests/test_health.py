"""健康检查端点冒烟测试。"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_liveness(test_client: AsyncClient):
    """测试 /health 端点返回 200。"""
    resp = await test_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_health_readiness(test_client: AsyncClient):
    """测试 /health/ready 端点返回数据库和 Redis 状态。"""
    resp = await test_client.get("/health/ready")
    # 可能返回 200 或 503（取决于依赖是否可用）
    assert resp.status_code in (200, 503)
    # 响应可能是 tuple (data, status_code) 或直接是 data
    data = resp.json()
    if isinstance(data, list):
        data = data[0]  # 取 tuple 中的第一个元素
    assert "status" in data
    assert "checks" in data
    # 至少应该检查 database 和 redis
    assert "database" in data["checks"]
    assert "redis" in data["checks"]


@pytest.mark.asyncio
async def test_auth_register_and_login(test_client: AsyncClient):
    """测试注册和登录基本流程。"""
    import uuid
    unique_id = uuid.uuid4().hex[:8]

    # 注册
    register_data = {
        "username": f"smoke_{unique_id}",
        "password": "SmokeTest123",
    }
    resp = await test_client.post("/api/v1/auth/register", json=register_data)
    assert resp.status_code in (200, 201), f"注册失败: {resp.text}"
    data = resp.json()
    assert "token" in data or "access_token" in data

    # 登录
    login_data = {
        "username": register_data["username"],
        "password": register_data["password"],
    }
    resp = await test_client.post("/api/v1/auth/login", json=login_data)
    assert resp.status_code == 200, f"登录失败: {resp.text}"
    data = resp.json()
    assert "token" in data or "access_token" in data


@pytest.mark.asyncio
async def test_auth_protected_endpoint_without_token(test_client: AsyncClient):
    """测试未认证访问受保护端点返回 401。"""
    resp = await test_client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)
