import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user_required
from app.core.database import get_db
from app.mcp.manager import mcp_manager
from app.mcp.policy import classify_tool
from app.models.models import MCPServerConfig, SkillToolBinding, ToolDefinition, User
from app.schemas.schemas import MCPServerCreateRequest

router = APIRouter(prefix="/mcp-servers", tags=["MCP Servers"])


def _tool_dict(t: ToolDefinition) -> dict:
    return {
        "id": t.id, "tool_key": t.tool_key, "name": t.name, "namespace": t.namespace,
        "description": t.description, "input_schema": json.loads(t.input_schema_json or "{}"),
        "provider_type": t.provider_type, "read_only": t.read_only,
        "requires_confirmation": t.requires_confirmation, "enabled": t.enabled,
    }


def _server_dict(row: MCPServerConfig) -> dict:
    return {
        "id": row.id, "server_key": row.server_key, "name": row.name,
        "description": row.description, "transport": row.transport, "url": row.url,
        "command": row.command, "args": json.loads(row.args_json or "[]"),
        "headers": {key: "***" for key in json.loads(row.headers_json or "{}")},
        "oauth_enabled": bool(json.loads(row.oauth_json or "{}").get("enabled")),
        "enabled": row.enabled, "health_status": row.health_status,
        "last_error": row.last_error, "last_discovered_at": row.last_discovered_at,
    }


def _runtime_config(row: MCPServerConfig) -> dict:
    return {
        "server_key": row.server_key, "transport": row.transport, "url": row.url,
        "command": row.command, "args": json.loads(row.args_json or "[]"),
        "headers": json.loads(row.headers_json or "{}"), "enabled": row.enabled,
    }


@router.get("")
async def list_servers(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user_required)):
    rows = await db.execute(select(MCPServerConfig).order_by(MCPServerConfig.created_at.desc()))
    return [_server_dict(row) for row in rows.scalars().all()]


@router.get("/tools/all")
async def list_all_tools(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user_required)):
    rows = await db.execute(select(ToolDefinition).where(ToolDefinition.enabled == True).order_by(ToolDefinition.name))
    return [_tool_dict(row) for row in rows.scalars().all()]


@router.post("", status_code=201)
async def create_server(body: MCPServerCreateRequest, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user_required)):
    if (await db.execute(select(MCPServerConfig).where(MCPServerConfig.server_key == body.server_key))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="server_key 已存在")
    if body.transport != "http":
        raise HTTPException(status_code=422, detail="当前安全运行时仅开放 Streamable HTTP MCP")
    if body.oauth.get("enabled"):
        raise HTTPException(status_code=422, detail="OAuth MCP 尚未实现，请使用请求头令牌；系统不会伪装为已支持")
    row = MCPServerConfig(
        server_key=body.server_key, name=body.name, description=body.description,
        transport=body.transport, url=body.url, command=body.command,
        args_json=json.dumps(body.args), headers_json=json.dumps(body.headers),
        oauth_json=json.dumps(body.oauth), enabled=body.enabled,
    )
    db.add(row)
    await db.flush()
    try:
        await _discover_and_store(row, db, force=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"MCP 发现失败: {exc}") from exc
    return _server_dict(row)


async def _discover_and_store(row: MCPServerConfig, db: AsyncSession, force: bool) -> list[dict]:
    tools = await mcp_manager.discover(row.server_key, _runtime_config(row), force=force)
    seen: set[str] = set()
    for item in tools:
        tool_key = f"mcp:{row.server_key}:{item['original_name']}"
        seen.add(tool_key)
        result = await db.execute(select(ToolDefinition).where(ToolDefinition.tool_key == tool_key))
        tool = result.scalar_one_or_none() or ToolDefinition(tool_key=tool_key, name=item["name"])
        if tool.id is None:
            db.add(tool)
        tool.name = item["name"]
        tool.namespace = row.server_key
        tool.description = item.get("description", "")
        tool.input_schema_json = json.dumps(item.get("parameters", {}), ensure_ascii=False)
        annotations = item.get("annotations") or {}
        tool.annotations_json = json.dumps(annotations, ensure_ascii=False)
        tool.provider_type = "mcp"
        tool.provider_id = row.id
        tool.read_only, tool.requires_confirmation = classify_tool(tool.name, annotations)
        tool.enabled = True
    existing = await db.execute(select(ToolDefinition).where(ToolDefinition.provider_id == row.id))
    for tool in existing.scalars().all():
        if tool.tool_key not in seen:
            tool.enabled = False
    row.health_status = "healthy"
    row.last_error = ""
    row.last_discovered_at = datetime.now(timezone.utc)
    await db.flush()
    return tools


@router.post("/{server_key}/discover")
async def discover_server(server_key: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user_required)):
    row = (await db.execute(select(MCPServerConfig).where(MCPServerConfig.server_key == server_key))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")
    try:
        tools = await _discover_and_store(row, db, force=True)
        return {"status": "healthy", "count": len(tools), "tools": tools}
    except Exception as exc:
        row.health_status = "unreachable"
        row.last_error = str(exc)
        return {"status": "unreachable", "error": str(exc)}


@router.post("/{server_key}/health")
async def check_server_health(
    server_key: str, db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user_required),
):
    row = (await db.execute(select(MCPServerConfig).where(
        MCPServerConfig.server_key == server_key
    ))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="MCP 服务不存在")
    try:
        tools = await _discover_and_store(row, db, force=True)
        return {"status": "healthy", "tools_count": len(tools)}
    except Exception as exc:
        row.health_status = "unreachable"
        row.last_error = str(exc)
        return {"status": "unreachable", "error": str(exc)}


@router.get("/{server_key}/tools")
async def list_server_tools(server_key: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user_required)):
    server = (await db.execute(select(MCPServerConfig).where(MCPServerConfig.server_key == server_key))).scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")
    rows = await db.execute(select(ToolDefinition).where(ToolDefinition.provider_id == server.id))
    return [_tool_dict(t) for t in rows.scalars().all()]


@router.post("/{server_key}/invoke")
async def invoke_server_tool(
    server_key: str, body: dict, db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user_required),
):
    server = (await db.execute(select(MCPServerConfig).where(
        MCPServerConfig.server_key == server_key
    ))).scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")
    tool_name = str(body.get("tool") or "")
    if not tool_name:
        raise HTTPException(status_code=422, detail="缺少 tool")
    tool = (await db.execute(select(ToolDefinition).where(
        ToolDefinition.provider_id == server.id,
        ToolDefinition.name == tool_name,
        ToolDefinition.enabled == True,
    ))).scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="该 MCP Server 未发现此工具")
    if tool.requires_confirmation and not body.get("confirmed"):
        return {"status": "confirmation_required", "error": "该工具需要明确确认", "tool": tool_name}
    return await mcp_manager.invoke(_runtime_config(server), tool.name, body.get("params") or {})


@router.delete("/{server_key}", status_code=204)
async def delete_server(server_key: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user_required)):
    row = (await db.execute(select(MCPServerConfig).where(MCPServerConfig.server_key == server_key))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")
    tool_ids = select(ToolDefinition.id).where(ToolDefinition.provider_id == row.id)
    await db.execute(delete(SkillToolBinding).where(SkillToolBinding.tool_id.in_(tool_ids)))
    await db.execute(delete(ToolDefinition).where(ToolDefinition.provider_id == row.id))
    await db.delete(row)
    mcp_manager.invalidate(server_key)
