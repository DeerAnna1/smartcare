"""OAuth credential storage broker."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import UserOAuthCredential


async def save_oauth_credential(
    db: AsyncSession,
    user_id: str,
    provider: str,
    access_token: str,
    refresh_token: str,
    expires_at: str,
    metadata: dict,
) -> UserOAuthCredential:
    result = await db.execute(
        select(UserOAuthCredential).where(
            UserOAuthCredential.user_id == user_id,
            UserOAuthCredential.provider == provider,
        )
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        cred = UserOAuthCredential(
            user_id=user_id,
            provider=provider,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        db.add(cred)
    else:
        cred.access_token = access_token
        cred.refresh_token = refresh_token
        cred.expires_at = expires_at
        cred.metadata_json = json.dumps(metadata, ensure_ascii=False)
    await db.flush()
    await db.refresh(cred)
    return cred
