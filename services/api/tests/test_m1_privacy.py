"""M1 隐私测试：同意管理、数据导出、账户删除。"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_consent_grant_and_list(test_client: AsyncClient, test_user: dict):
    """授予同意并列出。"""
    headers = {"Authorization": f"Bearer {test_user['token']}"}

    # 授予同意
    resp = await test_client.post(
        "/api/v1/privacy/consent",
        json={"consent_type": "upload_doc", "granted": True},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["consent_type"] == "upload_doc"
    assert data["granted"] is True

    # 列出同意
    resp = await test_client.get("/api/v1/privacy/consent", headers=headers)
    assert resp.status_code == 200
    consents = resp.json()
    assert len(consents) >= 1
    assert any(c["consent_type"] == "upload_doc" for c in consents)


@pytest.mark.asyncio
async def test_consent_revoke(test_client: AsyncClient, test_user: dict):
    """撤回同意。"""
    headers = {"Authorization": f"Bearer {test_user['token']}"}

    # 先授予
    await test_client.post(
        "/api/v1/privacy/consent",
        json={"consent_type": "ocr", "granted": True},
        headers=headers,
    )

    # 撤回
    resp = await test_client.delete("/api/v1/privacy/consent/ocr", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"


@pytest.mark.asyncio
async def test_consent_requires_auth(test_client: AsyncClient):
    """同意接口需要鉴权。"""
    resp = await test_client.get("/api/v1/privacy/consent")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_data_export_request(test_client: AsyncClient, test_user: dict):
    """请求数据导出。"""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    resp = await test_client.post("/api/v1/privacy/export", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_data_export_requires_auth(test_client: AsyncClient):
    """数据导出需要鉴权。"""
    resp = await test_client.post("/api/v1/privacy/export")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_account_request(test_client: AsyncClient, test_user_b: dict):
    """请求账户删除。"""
    headers = {"Authorization": f"Bearer {test_user_b['token']}"}
    resp = await test_client.post("/api/v1/privacy/delete-account", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
