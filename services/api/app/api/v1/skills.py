"""Skill Runtime API"""
import json
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from app.core.database import get_db
from app.api.deps.auth import get_current_user_required
from app.models.models import (
    SkillPackage, ToolInvocationLog, User, UserOAuthCredential,
    ToolDefinition, SkillToolBinding, AgentSkillPolicy, MCPServerConfig,
)
from app.schemas.schemas import (
    CreateSkillRequest, SkillResponse,
    InvokeSkillRequest, InvokeSkillResponse,
    SkillToolBindingRequest, AgentSkillPolicyRequest,
)

router = APIRouter(prefix="/skills", tags=["Skill Runtime"])

BUILTIN_SKILL_TO_TOOL = {
    "drug-safety": "check_drug_interaction",
    "appointment-booking": "query_doctor_schedule",
}


@router.get("", response_model=list[SkillResponse])
async def list_skills(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SkillPackage).order_by(SkillPackage.created_at.desc()))
    skills = result.scalars().all()
    bindings = await db.execute(
        select(SkillToolBinding.skill_id, ToolDefinition)
        .join(ToolDefinition, ToolDefinition.id == SkillToolBinding.tool_id)
        .where(ToolDefinition.enabled == True)
    )
    tools_by_skill: dict[str, list[dict]] = {}
    for skill_db_id, tool in bindings.all():
        tools_by_skill.setdefault(skill_db_id, []).append({
            "name": tool.name, "description": tool.description,
            "parameters": json.loads(tool.input_schema_json or "{}"),
            "provider_type": tool.provider_type,
            "requires_confirmation": tool.requires_confirmation,
        })
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
            mcp_server=s.mcp_server,
            tools=tools_by_skill.get(s.id, []),
            source_type=s.source_type,
            source_scope=s.source_scope,
            instructions=s.instructions,
            package_path=s.package_path,
            created_at=s.created_at,
        )
        for s in skills
    ]


@router.get("/builtin-tools")
async def list_builtin_tools():
    """List the only internal executors that a built-in Skill may bind to."""
    from app.services.tool_registry import BUILTIN_TOOLS
    return [item["function"] for item in BUILTIN_TOOLS]


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

    from app.services.tool_registry import BUILTIN_TOOLS

    runtime_type = body.runtime_type
    # Backward compatibility for existing clients that only send mcp_server.
    if runtime_type == "manual" and body.mcp_server:
        runtime_type = "mcp"

    discovered_tools: list[dict] = []
    mcp_server = ""
    source_type = runtime_type
    if runtime_type == "builtin":
        definitions = {
            item["function"]["name"]: item["function"]
            for item in BUILTIN_TOOLS
        }
        definition = definitions.get(body.builtin_tool)
        if not definition:
            raise HTTPException(status_code=422, detail="请选择有效的项目内置执行器")
        discovered_tools = [{
            "name": definition["name"],
            "description": definition.get("description", ""),
            "parameters": definition.get("parameters", {"type": "object", "properties": {}}),
        }]
    elif runtime_type == "mcp":
        if not body.mcp_server.strip():
            raise HTTPException(status_code=422, detail="MCP Skill 必须填写 MCP 服务地址")
        from app.mcp.client import MCPClient
        try:
            discovered_tools = await MCPClient(body.mcp_server).list_tools()
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"MCP 服务连接失败: {exc}") from exc
        if not discovered_tools:
            raise HTTPException(status_code=422, detail="MCP 服务未返回任何工具，未创建技能")
        mcp_server = body.mcp_server.strip()
    elif body.tools:
        raise HTTPException(status_code=422, detail="纯手动 Skill 不能注册可执行工具")

    skill = SkillPackage(
        skill_id=body.skill_id,
        name=body.name,
        description=body.description,
        category=body.category,
        confirm_required=body.confirm_required,
        source_url=body.source_url,
        source_type=source_type,
        source_scope="custom",
        instructions=body.instructions,
        keywords=json.dumps(body.keywords, ensure_ascii=False),
        trigger_examples=json.dumps(body.trigger_examples, ensure_ascii=False),
        version=body.version,
        mcp_server=mcp_server,
        tools=json.dumps(discovered_tools, ensure_ascii=False),
        degrade_policy=json.dumps(body.degrade_policy, ensure_ascii=False),
        status="ACTIVE",
    )
    db.add(skill)
    await db.flush()
    if runtime_type == "builtin" and body.builtin_tool:
        tool = (await db.execute(select(ToolDefinition).where(
            ToolDefinition.tool_key == f"builtin:{body.builtin_tool}"
        ))).scalar_one_or_none()
        if tool:
            db.add(SkillToolBinding(skill_id=skill.id, tool_id=tool.id, required=True))
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
        mcp_server=skill.mcp_server,
        tools=json.loads(skill.tools or "[]"),
        source_type=skill.source_type,
        source_scope=skill.source_scope,
        instructions=skill.instructions,
        package_path=skill.package_path,
        created_at=skill.created_at,
    )


@router.post("/packages/install", status_code=201)
async def install_skill_package(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user_required),
):
    from app.skills.installer import SkillInstallError, install_skill_archive
    from app.skills.loader import sync_skill_packages
    if not (file.filename or "").endswith((".skill", ".zip")):
        raise HTTPException(status_code=422, detail="仅支持 .skill 或 .zip")
    data = await file.read(6 * 1024 * 1024)
    try:
        target = install_skill_archive(data)
        loaded = await sync_skill_packages(db)
    except SkillInstallError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "path": str(target), "skills": [item.name for item in loaded]}


@router.get("/{skill_id}/bindings")
async def list_skill_bindings(skill_id: str, db: AsyncSession = Depends(get_db)):
    skill = (await db.execute(select(SkillPackage).where(SkillPackage.skill_id == skill_id))).scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")
    rows = await db.execute(
        select(ToolDefinition, SkillToolBinding)
        .join(SkillToolBinding, SkillToolBinding.tool_id == ToolDefinition.id)
        .where(SkillToolBinding.skill_id == skill.id)
    )
    return [{
        "id": tool.id, "tool_key": tool.tool_key, "name": tool.name,
        "description": tool.description, "provider_type": tool.provider_type,
        "required": binding.required, "permission": binding.permission,
    } for tool, binding in rows.all()]


@router.put("/{skill_id}/bindings")
async def update_skill_bindings(
    skill_id: str, body: SkillToolBindingRequest,
    db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user_required),
):
    skill = (await db.execute(select(SkillPackage).where(SkillPackage.skill_id == skill_id))).scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")
    tools = (await db.execute(select(ToolDefinition).where(ToolDefinition.id.in_(body.tool_ids)))).scalars().all()
    if len(tools) != len(set(body.tool_ids)):
        raise HTTPException(status_code=422, detail="包含不存在的 Tool")
    await db.execute(delete(SkillToolBinding).where(SkillToolBinding.skill_id == skill.id))
    for tool in tools:
        db.add(SkillToolBinding(skill_id=skill.id, tool_id=tool.id))
    return {"success": True, "count": len(tools)}


@router.get("/agent-policies/{agent_name}")
async def get_agent_policy(agent_name: str, db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(SkillPackage.skill_id)
        .join(AgentSkillPolicy, AgentSkillPolicy.skill_id == SkillPackage.id)
        .where(AgentSkillPolicy.agent_name == agent_name, AgentSkillPolicy.enabled == True)
    )
    return {"agent_name": agent_name, "skill_ids": list(rows.scalars().all())}


@router.put("/agent-policies/{agent_name}")
async def update_agent_policy(
    agent_name: str, body: AgentSkillPolicyRequest,
    db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user_required),
):
    skills = (await db.execute(select(SkillPackage).where(SkillPackage.skill_id.in_(body.skill_ids)))).scalars().all()
    if len(skills) != len(set(body.skill_ids)):
        raise HTTPException(status_code=422, detail="包含不存在的 Skill")
    await db.execute(delete(AgentSkillPolicy).where(AgentSkillPolicy.agent_name == agent_name))
    for skill in skills:
        db.add(AgentSkillPolicy(agent_name=agent_name, skill_id=skill.id, enabled=True))
    return {"success": True, "agent_name": agent_name, "count": len(skills)}


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

    bound_result = await db.execute(
        select(ToolDefinition, MCPServerConfig)
        .join(SkillToolBinding, SkillToolBinding.tool_id == ToolDefinition.id)
        .outerjoin(MCPServerConfig, MCPServerConfig.id == ToolDefinition.provider_id)
        .where(SkillToolBinding.skill_id == skill.id, ToolDefinition.enabled == True)
    )
    bound_tools = bound_result.all()
    requested_name = body.input.get("tool")
    if not requested_name and len(bound_tools) == 1:
        requested_name = bound_tools[0][0].name
    selected = next(((tool, server) for tool, server in bound_tools if tool.name == requested_name), None)
    builtin_tool_name = requested_name or BUILTIN_SKILL_TO_TOOL.get(skill.skill_id)

    if selected and selected[0].requires_confirmation and not body.input.get("confirmed"):
        result_data = {"status": "confirmation_required", "error": "该工具需要确认，请增加 confirmed=true"}
        status = "failed"
    elif selected and selected[0].provider_type == "builtin":
        from app.services.tool_registry import execute_tool_call
        result_data = await execute_tool_call(
            selected[0].name,
            body.input.get("params", body.input),
            db_session=db,
            user_id=user.id,
        )
        status = "failed" if result_data.get("status") == "failed" or result_data.get("error") else "success"
    elif selected and selected[0].provider_type == "mcp" and selected[1]:
        from app.mcp.manager import mcp_manager
        server = selected[1]
        try:
            result_data = await mcp_manager.invoke({
                "server_key": server.server_key, "transport": server.transport,
                "url": server.url, "headers": json.loads(server.headers_json or "{}"),
                "enabled": server.enabled,
            }, selected[0].name, body.input.get("params", {}))
            status = "success" if result_data.get("status") == "success" else "failed"
        except Exception as exc:
            result_data = {"error": str(exc)}
            status = "failed"
    else:
        result_data = {"error": "该 Skill 未绑定可执行工具；请先绑定内置工具或 MCP 工具"}
        status = "failed"

    latency_ms = int((time.time() - start) * 1000)

    # 记录调用日志
    log = ToolInvocationLog(
        skill_id=skill.id,
        trace_id=trace_id,
        tool_name=body.input.get("tool", builtin_tool_name or skill.name),
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
    await db.execute(delete(SkillToolBinding).where(SkillToolBinding.skill_id == skill.id))
    await db.execute(delete(AgentSkillPolicy).where(AgentSkillPolicy.skill_id == skill.id))
    await db.execute(delete(ToolInvocationLog).where(ToolInvocationLog.skill_id == skill.id))
    await db.delete(skill)
    await db.commit()


@router.get("/mcp-services")
async def list_mcp_services(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """列出所有已注册的 MCP 服务。"""
    from app.models.models import SkillPackage

    q = select(SkillPackage).where(SkillPackage.mcp_server != None, SkillPackage.mcp_server != "")
    result = await db.execute(q)
    skills = result.scalars().all()

    return [
        {
            "id": s.id,
            "skill_id": s.skill_id,
            "name": s.name,
            "description": s.description,
            "mcp_server": s.mcp_server,
            "tools": json.loads(s.tools or "[]"),
            "status": s.status,
            "source_type": s.source_type,
        }
        for s in skills
    ]


@router.get("/{skill_id}/health")
async def check_skill_health(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """检查 MCP 服务健康状态。"""
    from app.models.models import SkillPackage

    q = select(SkillPackage).where(SkillPackage.skill_id == skill_id)
    result = await db.execute(q)
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    if not skill.mcp_server:
        return {"status": "no_server", "message": "未配置 MCP 服务端点"}

    from app.mcp.client import MCPClient
    return await MCPClient(skill.mcp_server).health_check()


@router.post("/{skill_id}/test")
async def test_skill(
    skill_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """通过真实 MCP 服务测试工具，并记录实际结果。"""
    from app.models.models import SkillPackage, ToolInvocationLog
    from app.mcp.client import MCPClient

    q = select(SkillPackage).where(SkillPackage.skill_id == skill_id)
    result = await db.execute(q)
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    if not skill.mcp_server:
        raise HTTPException(status_code=400, detail="该技能未配置 MCP 服务")
    tools = json.loads(skill.tools or "[]")
    tool_name = body.get("tool")
    if not tool_name and len(tools) == 1:
        tool_name = tools[0].get("name")
    if not tool_name:
        raise HTTPException(status_code=400, detail="请指定 tool；该 MCP 服务包含多个工具")
    params = body.get("params", {})
    started = time.time()
    try:
        response = await MCPClient(skill.mcp_server).call_tool(tool_name, params)
        result_status = response.get("status", "failed")
        error_reason = None
    except Exception as exc:
        response = {"status": "failed", "error": str(exc)}
        result_status = "failed"
        error_reason = str(exc)
    log = ToolInvocationLog(
        skill_id=skill.id,
        tool_name=tool_name,
        request_json=json.dumps(params, ensure_ascii=False),
        response_json=json.dumps(response, ensure_ascii=False),
        latency_ms=int((time.time() - started) * 1000),
        result_status=result_status,
        error_reason=error_reason,
    )
    db.add(log)
    await db.commit()

    return response


@router.post("/builtin/tools/test")
async def test_builtin_tool(
    body: dict,
    user: User = Depends(get_current_user_required),
):
    """直接测试内置工具（药物相互作用、排班查询、挂号锁定）。"""
    from app.services.tool_registry import execute_tool_call

    tool_name = body.get("tool", "")
    params = body.get("params", {})

    if not tool_name:
        raise HTTPException(status_code=400, detail="缺少 tool 参数")

    result = await execute_tool_call(tool_name, params)
    return result
