from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.models import User
from app.services.auth import decode_access_token


async def get_current_user(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Get current user from Authorization header or token query parameter."""
    auth_token = None

    # Try Authorization header first
    if authorization:
        scheme, _, auth_token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not auth_token:
            auth_token = None

    # Fall back to query parameter
    if not auth_token and token:
        auth_token = token

    if not auth_token:
        return None

    payload = decode_access_token(auth_token)
    result = await db.execute(select(User).where(User.id == payload["user_id"]))
    user = result.scalar_one_or_none()
    return user


async def get_current_user_required(
    current_user: User | None = Depends(get_current_user),
) -> User:
    if current_user is not None:
        return current_user
    raise HTTPException(status_code=401, detail="请先登录")


async def get_current_admin_user(
    current_user: User = Depends(get_current_user_required),
) -> User:
    """要求当前用户为管理员角色。"""
    if current_user.role == "admin":
        return current_user
    raise HTTPException(status_code=403, detail="需要管理员权限")


# Backward-compatible alias for older imports.
get_current_or_default_user = get_current_user_required
