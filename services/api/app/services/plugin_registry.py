"""Plugin manifest registry."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import SkillPackage


async def upsert_plugin_skill(
    db: AsyncSession,
    provider: str,
    auth_type: str,
    manifest: dict,
) -> SkillPackage:
    skill_id = f"plugin-{provider}"
    result = await db.execute(select(SkillPackage).where(SkillPackage.skill_id == skill_id))
    skill = result.scalar_one_or_none()
    tools = manifest.get("tools", [])
    if skill is None:
        skill = SkillPackage(
            skill_id=skill_id,
            name=manifest.get("name") or provider,
            description=manifest.get("description") or f"{provider} plugin",
            category="第三方插件",
            keywords=json.dumps(manifest.get("keywords", []), ensure_ascii=False),
            trigger_examples=json.dumps(manifest.get("trigger_examples", []), ensure_ascii=False),
            confirm_required=manifest.get("confirm_required", True),
            tools=json.dumps(tools, ensure_ascii=False),
            source_type="plugin",
            source_url=manifest.get("base_url", ""),
            mcp_server=provider,
            manifest_json=json.dumps(
                {"provider": provider, "auth_type": auth_type, "manifest": manifest},
                ensure_ascii=False,
            ),
            status="ACTIVE",
        )
        db.add(skill)
    else:
        skill.name = manifest.get("name") or skill.name
        skill.description = manifest.get("description") or skill.description
        skill.tools = json.dumps(tools, ensure_ascii=False)
        skill.manifest_json = json.dumps(
            {"provider": provider, "auth_type": auth_type, "manifest": manifest},
            ensure_ascii=False,
        )
    await db.flush()
    await db.refresh(skill)
    return skill
