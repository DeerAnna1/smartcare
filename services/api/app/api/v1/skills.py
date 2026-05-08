"""Skill Runtime API"""
import json
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.api.deps.auth import get_current_user_required
from app.models.models import SkillPackage, ToolInvocationLog, User, UserOAuthCredential
from app.schemas.schemas import (
    CreateSkillRequest, SkillResponse,
    InvokeSkillRequest, InvokeSkillResponse,
)

router = APIRouter(prefix="/skills", tags=["Skill Runtime"])


@router.get("", response_model=list[SkillResponse])
async def list_skills(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SkillPackage).order_by(SkillPackage.created_at.desc()))
    skills = result.scalars().all()
    return [
        SkillResponse(
            id=s.id,
            skill_id=s.skill_id,
            name=s.name,
            description=s.description,
            category=s.category,
            status=s.status,
            confirm_required=s.confirm_required,
            version=s.version,
            keywords=json.loads(s.keywords),
            trigger_examples=json.loads(s.trigger_examples),
            created_at=s.created_at,
        )
        for s in skills
    ]


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    body: CreateSkillRequest,
    db: AsyncSession = Depends(get_db),
):
    # Unique constraint check
    existing = await db.execute(
        select(SkillPackage).where(SkillPackage.skill_id == body.skill_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"skill_id '{body.skill_id}' 已存在")

    skill = SkillPackage(
        skill_id=body.skill_id,
        name=body.name,
        description=body.description,
        category=body.category,
        confirm_required=body.confirm_required,
        source_url=body.source_url,
        source_type="repo" if body.source_url else "manual",
        keywords=json.dumps(body.keywords, ensure_ascii=False),
        trigger_examples=json.dumps(body.trigger_examples, ensure_ascii=False),
        version=body.version,
        mcp_server=body.mcp_server,
        tools=json.dumps(body.tools, ensure_ascii=False),
        degrade_policy=json.dumps(body.degrade_policy, ensure_ascii=False),
        status="ACTIVE",
    )
    db.add(skill)
    await db.flush()
    await db.refresh(skill)
    return SkillResponse(
        id=skill.id,
        skill_id=skill.skill_id,
        name=skill.name,
        description=skill.description,
        category=skill.category,
        status=skill.status,
        confirm_required=skill.confirm_required,
        version=skill.version,
        keywords=json.loads(skill.keywords),
        trigger_examples=json.loads(skill.trigger_examples),
        created_at=skill.created_at,
    )


@router.post("/{skill_id}/invoke", response_model=InvokeSkillResponse)
async def invoke_skill(
    skill_id: str,
    body: InvokeSkillRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """Skill Runtime §10.4 路由顺序执行"""
    result = await db.execute(
        select(SkillPackage).where(SkillPackage.skill_id == skill_id)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")

    if skill.status != "ACTIVE":
        raise HTTPException(status_code=400, detail=f"Skill 状态为 {skill.status}，不可调用")

    # 第三方插件 OAuth 检查
    manifest = json.loads(skill.manifest_json or "{}")
    provider = manifest.get("provider")
    auth_type = manifest.get("auth_type", "none")
    if skill.source_type == "plugin" and auth_type == "oauth2" and provider:
        cred_res = await db.execute(
            select(UserOAuthCredential).where(
                UserOAuthCredential.user_id == user.id,
                UserOAuthCredential.provider == provider,
            )
        )
        if cred_res.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail=f"插件 {provider} 需要先完成 OAuth 授权")

    # confirm_required 检查
    if skill.confirm_required and not body.input.get("confirmed"):
        return InvokeSkillResponse(
            skill_id=skill_id,
            status="failed",
            error="此 Skill 需要用户二次确认，请在 input 中传入 confirmed=true",
            trace_id=body.trace_id,
        )

    trace_id = body.trace_id or str(uuid.uuid4())
    start = time.time()

    # MCP 调用（当前阶段：若有 mcp_server 则尝试，否则返回 degraded）
    if skill.mcp_server:
        # TODO: 接入真实 MCP Gateway（Phase 2）
        result_data = {"message": "MCP Gateway 尚未接入，已降级", "mcp_server": skill.mcp_server}
        status = "degraded"
    else:
        result_data = {"message": f"Skill '{skill.name}' 已触发（手动注册，无 MCP 端点）"}
        status = "success"

    latency_ms = int((time.time() - start) * 1000)

    # 记录调用日志
    log = ToolInvocationLog(
        skill_id=skill.id,
        trace_id=trace_id,
        tool_name=skill.name,
        request_json=json.dumps(body.input, ensure_ascii=False),
        response_json=json.dumps(result_data, ensure_ascii=False),
        latency_ms=latency_ms,
        result_status=status,
    )
    db.add(log)
    await db.flush()

    return InvokeSkillResponse(
        skill_id=skill_id,
        status=status,  # type: ignore[arg-type]
        result=result_data,
        trace_id=trace_id,
    )


@router.get("/{skill_id}/logs")
async def get_skill_logs(skill_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SkillPackage).where(SkillPackage.skill_id == skill_id)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")

    logs_result = await db.execute(
        select(ToolInvocationLog)
        .where(ToolInvocationLog.skill_id == skill.id)
        .order_by(ToolInvocationLog.created_at.desc())
    )
    logs = logs_result.scalars().all()
    return [
        {
            "id": lg.id,
            "trace_id": lg.trace_id,
            "tool_name": lg.tool_name,
            "latency_ms": lg.latency_ms,
            "result_status": lg.result_status,
            "error_reason": lg.error_reason,
            "created_at": lg.created_at.isoformat(),
        }
        for lg in logs
    ]


@router.patch("/{skill_id}/status")
async def update_skill_status(
    skill_id: str,
    status: str,
    db: AsyncSession = Depends(get_db),
):
    """Toggle skill status: ACTIVE / DISABLED"""
    if status not in ("ACTIVE", "DISABLED"):
        raise HTTPException(status_code=400, detail="status 只能为 ACTIVE 或 DISABLED")
    result = await db.execute(
        select(SkillPackage).where(SkillPackage.skill_id == skill_id)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")
    skill.status = status
    await db.flush()
    await db.commit()
    return {"success": True, "skill_id": skill_id, "status": status}


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a skill package"""
    result = await db.execute(
        select(SkillPackage).where(SkillPackage.skill_id == skill_id)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")
    await db.delete(skill)
    await db.commit()
