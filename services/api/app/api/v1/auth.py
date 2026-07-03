"""用户认证 API"""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.models import User
from app.schemas.schemas import AuthResponse, LoginRequest, RegisterRequest, UserProfileResponse
from app.services.auth import create_access_token, hash_password, verify_password
from app.services.feishu_notifier import (
    get_patient_display_name,
    resolve_feishu_config,
    send_feishu_alert,
    validate_feishu_webhook_url,
)

router = APIRouter(prefix="/auth", tags=["用户认证"])


def to_user_profile(user: User) -> UserProfileResponse:
    profile = json.loads(user.profile or "{}")
    try:
        preferences = json.loads(user.preferences or "{}") if user.preferences else {}
    except json.JSONDecodeError:
        preferences = {}
    return UserProfileResponse(
        user_id=user.id,
        username=user.account_id,
        display_name=profile.get("name") or user.account_id,
        avatar_url=preferences.get("avatar_url") or "",
        created_at=user.created_at,
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.account_id == body.username.strip()))
    existing_user = result.scalar_one_or_none()
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="用户名已存在")

    user = User(
        account_id=body.username.strip(),
        password_hash=hash_password(body.password),
        profile=json.dumps({"name": body.username.strip()}, ensure_ascii=False),
    )
    db.add(user)
    await db.flush()
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id, user.account_id)
    return AuthResponse(token=token, user=to_user_profile(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.account_id == body.username.strip()))
    user = result.scalar_one_or_none()
    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(user.id, user.account_id)
    return AuthResponse(token=token, user=to_user_profile(user))


@router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: User | None = Depends(get_current_user)):
    if current_user is None:
        raise HTTPException(status_code=401, detail="未登录")
    return to_user_profile(current_user)


# ─── LLM 配置 ─────────────────────────────────────────────────────────────

class LLMConfigResponse(BaseModel):
    has_config: bool
    api_key_masked: str = ""
    base_url: str
    model: str
    asr_model: str = ""
    asr_base_url: str = ""
    tts_model: str = ""
    tts_base_url: str = ""
    omni_model: str = ""
    omni_base_url: str = ""


class LLMConfigUpdateRequest(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    asr_model: str = ""
    asr_base_url: str = ""
    tts_model: str = ""
    tts_base_url: str = ""
    omni_model: str = ""
    omni_base_url: str = ""


@router.get("/llm-config", response_model=LLMConfigResponse)
async def get_llm_config(current_user: User = Depends(get_current_user)):
    if current_user is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        prefs = json.loads(current_user.preferences or "{}")
    except json.JSONDecodeError:
        prefs = {}
    llm_cfg = prefs.get("llm_config", {})
    api_key = llm_cfg.get("api_key", "")
    masked = api_key[:3] + "***" + api_key[-4:] if len(api_key) > 7 else ("***" if api_key else "")
    return LLMConfigResponse(
        has_config=bool(api_key),
        api_key_masked=masked,
        base_url=llm_cfg.get("base_url", ""),
        model=llm_cfg.get("model", ""),
        asr_model=llm_cfg.get("asr_model", ""),
        asr_base_url=llm_cfg.get("asr_base_url", ""),
        tts_model=llm_cfg.get("tts_model", ""),
        tts_base_url=llm_cfg.get("tts_base_url", ""),
        omni_model=llm_cfg.get("omni_model", ""),
        omni_base_url=llm_cfg.get("omni_base_url", ""),
    )


@router.put("/llm-config")
async def update_llm_config(
    body: LLMConfigUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user is None:
        raise HTTPException(status_code=401, detail="未登录")

    try:
        prefs = json.loads(current_user.preferences or "{}")
    except json.JSONDecodeError:
        prefs = {}

    existing = prefs.get("llm_config", {})

    # 如果 api_key 为空且已有配置，保留旧 api_key（允许不修改密钥时只改 URL/模型）
    api_key = body.api_key.strip() if body.api_key.strip() else existing.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")
    if not body.base_url.strip():
        raise HTTPException(status_code=400, detail="Base URL 不能为空")
    if not body.model.strip():
        raise HTTPException(status_code=400, detail="模型名称不能为空")

    base_url = body.base_url.strip().rstrip("/")
    prefs["llm_config"] = {
        "api_key": api_key,
        "base_url": base_url,
        "model": body.model.strip(),
        "asr_model": body.asr_model.strip(),
        "asr_base_url": (body.asr_base_url.strip().rstrip("/") if body.asr_base_url.strip() else ""),
        "tts_model": body.tts_model.strip(),
        "tts_base_url": (body.tts_base_url.strip().rstrip("/") if body.tts_base_url.strip() else ""),
        "omni_model": body.omni_model.strip(),
        "omni_base_url": (body.omni_base_url.strip().rstrip("/") if body.omni_base_url.strip() else ""),
    }
    current_user.preferences = json.dumps(prefs, ensure_ascii=False)
    await db.commit()
    return {"status": "saved"}


# ─── 飞书 Webhook 配置 ──────────────────────────────────────────────────────

class FeishuConfigResponse(BaseModel):
    webhook_url: str = ""
    enabled: bool = False
    secret_configured: bool = False


class FeishuConfigUpdateRequest(BaseModel):
    webhook_url: str = ""
    enabled: bool = False
    webhook_secret: str | None = None


@router.get("/feishu-config", response_model=FeishuConfigResponse)
async def get_feishu_config(current_user: User = Depends(get_current_user)):
    if current_user is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        prefs = json.loads(current_user.preferences or "{}")
    except json.JSONDecodeError:
        prefs = {}
    feishu_cfg = prefs.get("feishu_config", {})
    return FeishuConfigResponse(
        webhook_url=feishu_cfg.get("webhook_url", ""),
        enabled=feishu_cfg.get("enabled", False),
        secret_configured=bool(feishu_cfg.get("webhook_secret", "")),
    )


@router.put("/feishu-config")
async def update_feishu_config(
    body: FeishuConfigUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        prefs = json.loads(current_user.preferences or "{}")
    except json.JSONDecodeError:
        prefs = {}

    webhook_url = body.webhook_url.strip()
    if webhook_url and not validate_feishu_webhook_url(webhook_url):
        raise HTTPException(status_code=400, detail="请输入有效的飞书自定义机器人 Webhook URL")
    if body.enabled and not webhook_url:
        raise HTTPException(status_code=400, detail="启用飞书告警前必须填写 Webhook URL")

    existing = prefs.get("feishu_config", {})
    webhook_secret = (
        body.webhook_secret.strip()
        if body.webhook_secret is not None and body.webhook_secret.strip()
        else existing.get("webhook_secret", "")
    )
    prefs["feishu_config"] = {
        "webhook_url": webhook_url,
        "webhook_secret": webhook_secret,
        "enabled": body.enabled,
    }
    current_user.preferences = json.dumps(prefs, ensure_ascii=False)
    await db.commit()
    return {"status": "saved"}


@router.post("/feishu-config/test")
async def test_feishu_config(current_user: User = Depends(get_current_user)):
    if current_user is None:
        raise HTTPException(status_code=401, detail="未登录")

    config = resolve_feishu_config(current_user)
    if not config.enabled or not config.webhook_url:
        raise HTTPException(status_code=400, detail="请先保存并启用飞书告警")

    result = await send_feishu_alert(
        webhook_url=config.webhook_url,
        webhook_secret=config.webhook_secret,
        patient_name=get_patient_display_name(current_user),
        risk_level="high",
        reason="飞书 Webhook 配置测试",
        evidence=["这是一条测试告警，不代表真实医疗风险"],
        session_id="configuration-test",
    )
    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"飞书发送失败：{result['error']}")
    return {"status": "success"}
