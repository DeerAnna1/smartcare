"""Plugin market and OAuth APIs."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user_required
from app.core.database import get_db
from app.models.models import SkillPackage, User, UserOAuthCredential
from app.schemas.schemas import OAuthConnectRequest, PluginManifestRequest
from app.services.oauth_broker import save_oauth_credential
from app.services.plugin_registry import upsert_plugin_skill

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.post("/manifest")
async def register_plugin_manifest(
    body: PluginManifestRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    skill = await upsert_plugin_skill(
        db=db,
        provider=body.provider,
        auth_type=body.auth_type,
        manifest=body.manifest,
    )
    return {"success": True, "skill_id": skill.skill_id, "name": skill.name}


@router.post("/oauth/connect")
async def connect_oauth_provider(
    body: OAuthConnectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    cred = await save_oauth_credential(
        db=db,
        user_id=user.id,
        provider=body.provider,
        access_token=body.access_token,
        refresh_token=body.refresh_token,
        expires_at=body.expires_at,
        metadata=body.metadata,
    )
    return {"success": True, "credential_id": cred.id, "provider": cred.provider}


@router.get("/oauth/providers")
async def list_connected_providers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(UserOAuthCredential).where(UserOAuthCredential.user_id == user.id)
    )
    rows = result.scalars().all()
    return [
        {"provider": row.provider, "expires_at": row.expires_at, "updated_at": row.updated_at.isoformat()}
        for row in rows
    ]


@router.get("/market")
async def list_plugin_market(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SkillPackage).where(SkillPackage.source_type == "plugin", SkillPackage.status == "ACTIVE")
    )
    rows = result.scalars().all()
    return [
        {
            "skill_id": row.skill_id,
            "name": row.name,
            "description": row.description,
            "manifest": json.loads(row.manifest_json or "{}"),
        }
        for row in rows
    ]
