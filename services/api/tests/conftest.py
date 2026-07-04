"""
测试 fixture 配置。

提供：
- test_db: 独立的数据库会话，测试后自动回滚
- test_client: FastAPI 异步测试客户端
- test_user / test_user_b: 测试用户和 token
"""

import os
import uuid
from typing import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db

# 导入所有模型以注册到 Base.metadata
import app.models.models  # noqa: F401

# 导入 FastAPI app（放在最后避免循环导入）
from app.main import app as fastapi_app

# CI 通过 DATABASE_URL 注入 5432；本地 Docker 默认映射到 5433。
TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://medhelp:medhelp_secret@localhost:5433/medhelpagent_test",
)


@pytest_asyncio.fixture
async def test_engine():
    """创建测试数据库引擎。"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # 清理：删除所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """每个测试用例独立的数据库会话。"""
    async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def test_client(test_db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI 异步测试客户端，使用测试数据库。"""

    def _override_get_db():
        return test_db

    fastapi_app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(test_client: AsyncClient) -> dict:
    """创建测试用户并返回 token。"""
    unique_id = uuid.uuid4().hex[:8]
    register_data = {
        "username": f"testuser_{unique_id}",
        "password": "TestPass123",
    }

    # 注册
    resp = await test_client.post("/api/v1/auth/register", json=register_data)
    assert resp.status_code in (200, 201), f"注册失败: {resp.text}"

    # 登录
    login_data = {
        "username": register_data["username"],
        "password": register_data["password"],
    }
    resp = await test_client.post("/api/v1/auth/login", json=login_data)
    assert resp.status_code == 200, f"登录失败: {resp.text}"

    token = resp.json().get("access_token") or resp.json().get("token")
    assert token, "登录响应中没有 token"

    return {
        "username": register_data["username"],
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest_asyncio.fixture
async def test_user_b(test_client: AsyncClient) -> dict:
    """创建第二个测试用户，用于跨用户隔离测试。"""
    unique_id = uuid.uuid4().hex[:8]
    register_data = {
        "username": f"testuser_b_{unique_id}",
        "password": "TestPass456",
    }

    # 注册
    resp = await test_client.post("/api/v1/auth/register", json=register_data)
    assert resp.status_code in (200, 201), f"注册失败: {resp.text}"

    # 登录
    login_data = {
        "username": register_data["username"],
        "password": register_data["password"],
    }
    resp = await test_client.post("/api/v1/auth/login", json=login_data)
    assert resp.status_code == 200, f"登录失败: {resp.text}"

    token = resp.json().get("access_token") or resp.json().get("token")
    assert token, "登录响应中没有 token"

    return {
        "username": register_data["username"],
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }
