"""默认用户服务（单用户开发模式）"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import User

DEFAULT_ACCOUNT_ID = "default-user"


async def get_or_create_default_user(db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(User.account_id == DEFAULT_ACCOUNT_ID)
    )
    user = result.scalar_one_or_none()
    if not user:
        user = User(account_id=DEFAULT_ACCOUNT_ID, profile='{"name": "默认用户"}')
        db.add(user)
        await db.flush()
        await db.refresh(user)
    return user
