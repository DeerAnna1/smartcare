"""用户认证 API"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.models import User
from app.schemas.schemas import AuthResponse, LoginRequest, RegisterRequest, UserProfileResponse
from app.services.auth import create_access_token, hash_password, verify_password

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
