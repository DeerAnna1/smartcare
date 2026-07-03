"""Synchronize file-backed Skills and executable Tool definitions."""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    AgentSkillPolicy, MCPServerConfig, SkillPackage, SkillToolBinding,
    ToolDefinition, ToolInvocationLog,
)
from app.mcp.policy import classify_tool
from app.services.tool_registry import BUILTIN_TOOLS
from app.skills.loader import sync_skill_packages


DEFAULT_BINDINGS = {
    # drug-safety 使用 MCP openfda-drug-safety 服务，不绑定内置工具
    "appointment-booking": ("query_doctor_schedule", "lock_appointment_slot"),
}

SKILL_CHAT_EXAMPLES = {
    "drug-safety": ["检查阿莫西林和布洛芬是否存在药物相互作用，并说明数据来源。"],
    "medical-literature-review": ["搜索高血压生活方式干预相关医学研究，返回3篇并标注 PMID。"],
    "healthcare-queue-simulator": ["模拟急诊科每小时8名患者、3名医生运行1天，返回平均等待时间。"],
    "healthcare-provider-directory": ["查询美国德州的医疗账单服务机构，返回3家并列出名称和网址。"],
    "appointment-booking": ["查询明天心内科的医生排班，列出可预约时段。"],
    "task-sync": ["每天上午8点提醒我按医嘱服药，并创建周期性健康任务。"],
    "cross-app-agent": ["打开医院应用并进入电子处方页面；执行任何提交操作前先让我确认。"],
}


async def _merge_skill_alias(db: AsyncSession, alias: str, canonical: str) -> None:
    source = (await db.execute(select(SkillPackage).where(
        SkillPackage.skill_id == alias
    ))).scalar_one_or_none()
    target = (await db.execute(select(SkillPackage).where(
        SkillPackage.skill_id == canonical
    ))).scalar_one_or_none()
    if not source or not target or source.id == target.id:
        return
    target_keywords = set(json.loads(target.keywords or "[]"))
    target_keywords.update(json.loads(source.keywords or "[]"))
    target.keywords = json.dumps(sorted(target_keywords), ensure_ascii=False)
    target_examples = list(dict.fromkeys([
        *json.loads(target.trigger_examples or "[]"),
        *json.loads(source.trigger_examples or "[]"),
    ]))
    target.trigger_examples = json.dumps(target_examples, ensure_ascii=False)
    if target.category == "通用" and source.category:
        target.category = source.category
    target.confirm_required = target.confirm_required or source.confirm_required
    bindings = (await db.execute(select(SkillToolBinding).where(
        SkillToolBinding.skill_id == source.id
    ))).scalars().all()
    for binding in bindings:
        exists = (await db.execute(select(SkillToolBinding.id).where(
            SkillToolBinding.skill_id == target.id,
            SkillToolBinding.tool_id == binding.tool_id,
        ))).scalar_one_or_none()
        if exists:
            await db.delete(binding)
        else:
            binding.skill_id = target.id
    policies = (await db.execute(select(AgentSkillPolicy).where(
        AgentSkillPolicy.skill_id == source.id
    ))).scalars().all()
    for policy in policies:
        exists = (await db.execute(select(AgentSkillPolicy.id).where(
            AgentSkillPolicy.agent_name == policy.agent_name,
            AgentSkillPolicy.skill_id == target.id,
        ))).scalar_one_or_none()
        if exists:
            await db.delete(policy)
        else:
            policy.skill_id = target.id
    logs = (await db.execute(select(ToolInvocationLog).where(
        ToolInvocationLog.skill_id == source.id
    ))).scalars().all()
    for log in logs:
        log.skill_id = target.id
    await db.flush()
    await db.delete(source)


async def _delete_skill(db: AsyncSession, skill_id: str) -> None:
    skill = (await db.execute(select(SkillPackage).where(
        SkillPackage.skill_id == skill_id
    ))).scalar_one_or_none()
    if not skill:
        return
    for model in (SkillToolBinding, AgentSkillPolicy, ToolInvocationLog):
        rows = (await db.execute(select(model).where(model.skill_id == skill.id))).scalars().all()
        for row in rows:
            await db.delete(row)
    await db.flush()
    await db.delete(skill)


async def _delete_test_mcp_servers(db: AsyncSession) -> None:
    servers = (await db.execute(select(MCPServerConfig))).scalars().all()
    for server in servers:
        identity = f"{server.server_key} {server.name}".casefold()
        if "mcp_test_tool" not in identity and "mcp测试工具" not in identity:
            continue
        tools = (await db.execute(select(ToolDefinition).where(
            ToolDefinition.provider_id == server.id
        ))).scalars().all()
        for tool in tools:
            bindings = (await db.execute(select(SkillToolBinding).where(
                SkillToolBinding.tool_id == tool.id
            ))).scalars().all()
            for binding in bindings:
                await db.delete(binding)
            await db.delete(tool)
        await db.flush()
        await db.delete(server)


def _clean_server_name(name: str, hint: str = "") -> str:
    cleaned = name.replace("（迁移）", "").replace("(migrated)", "").strip()
    if not cleaned:
        return "MCP 服务"
    lowered = f"{cleaned} {hint}".casefold()
    if "openfda" in lowered:
        return "药品安全数据服务（OpenFDA）"
    if "pubmed" in lowered:
        return "医学文献检索服务（PubMed）"
    if "healthcare-queue" in lowered or "queue-simulator" in lowered:
        return "医疗排队与人员配置模拟服务"
    if "healthcare-provider" in lowered or "provider-directory" in lowered:
        return "医疗服务机构目录服务"
    return cleaned if "MCP" in cleaned.upper() else f"{cleaned} MCP 服务"


def _original_tool_name(tool: ToolDefinition) -> str:
    if tool.tool_key.startswith("mcp:"):
        return tool.tool_key.rsplit(":", 1)[-1]
    return tool.name.split("__", 1)[-1]


async def _move_bindings(db: AsyncSession, source: ToolDefinition, target: ToolDefinition) -> None:
    bindings = (await db.execute(select(SkillToolBinding).where(
        SkillToolBinding.tool_id == source.id
    ))).scalars().all()
    for binding in bindings:
        exists = (await db.execute(select(SkillToolBinding.id).where(
            SkillToolBinding.skill_id == binding.skill_id,
            SkillToolBinding.tool_id == target.id,
        ))).scalar_one_or_none()
        if exists:
            await db.delete(binding)
        else:
            binding.tool_id = target.id


async def _merge_server(db: AsyncSession, source: MCPServerConfig, target: MCPServerConfig) -> None:
    source_tools = (await db.execute(select(ToolDefinition).where(
        ToolDefinition.provider_id == source.id
    ))).scalars().all()
    target_tools = (await db.execute(select(ToolDefinition).where(
        ToolDefinition.provider_id == target.id
    ))).scalars().all()
    target_by_original = {_original_tool_name(tool): tool for tool in target_tools}
    for tool in source_tools:
        original = _original_tool_name(tool)
        existing = target_by_original.get(original)
        if existing:
            await _move_bindings(db, tool, existing)
            await db.delete(tool)
        else:
            tool.provider_id = target.id
            tool.namespace = target.server_key
            tool.tool_key = f"mcp:{target.server_key}:{original}"
            tool.name = f"{target.server_key}__{original}"
    await db.flush()
    await db.delete(source)


async def _normalize_mcp_servers(db: AsyncSession) -> None:
    """Remove compatibility labels and merge duplicate endpoints without data loss."""
    servers = (await db.execute(select(MCPServerConfig).order_by(MCPServerConfig.created_at))).scalars().all()
    by_url: dict[str, MCPServerConfig] = {}
    for server in servers:
        normalized_url = server.url.rstrip("/").casefold()
        if not normalized_url:
            continue
        preferred = by_url.get(normalized_url)
        if preferred and preferred.id != server.id:
            # Prefer an explicitly named server over a compatibility key.
            if preferred.server_key.startswith("legacy-") and not server.server_key.startswith("legacy-"):
                await _merge_server(db, preferred, server)
                by_url[normalized_url] = server
            else:
                await _merge_server(db, server, preferred)
            continue
        by_url[normalized_url] = server

    await db.flush()
    remaining = (await db.execute(select(MCPServerConfig))).scalars().all()
    used_keys = {server.server_key for server in remaining}
    for server in remaining:
        server.name = _clean_server_name(server.name, f"{server.server_key} {server.url}")
        if not server.server_key.startswith("legacy-"):
            continue
        candidate = server.server_key.removeprefix("legacy-") or "mcp-server"
        if candidate in used_keys:
            candidate = f"{candidate}-server"
        used_keys.discard(server.server_key)
        used_keys.add(candidate)
        old_key = server.server_key
        server.server_key = candidate
        tools = (await db.execute(select(ToolDefinition).where(
            ToolDefinition.provider_id == server.id
        ))).scalars().all()
        for tool in tools:
            original = _original_tool_name(tool)
            tool.namespace = candidate
            tool.tool_key = f"mcp:{candidate}:{original}"
            tool.name = f"{candidate}__{original}"
        if old_key != candidate:
            server.last_error = ""


async def sync_extension_registry(db: AsyncSession) -> None:
    """Idempotently seed file Skills, built-in Tools, bindings and agent policy."""
    await sync_skill_packages(db)
    await _merge_skill_alias(db, "drug-interaction", "drug-safety")
    await _merge_skill_alias(db, "openfda-drug-safety", "drug-safety")
    await _merge_skill_alias(db, "pubmed-research", "medical-literature-review")
    await _delete_skill(db, "mcp_test_tool")
    await _delete_test_mcp_servers(db)
    tools_by_name: dict[str, ToolDefinition] = {}
    for item in BUILTIN_TOOLS:
        definition = item["function"]
        name = definition["name"]
        row = (await db.execute(
            select(ToolDefinition).where(ToolDefinition.tool_key == f"builtin:{name}")
        )).scalar_one_or_none()
        if row is None:
            row = ToolDefinition(tool_key=f"builtin:{name}", name=name)
            db.add(row)
        row.name = name
        row.namespace = "builtin"
        row.description = definition.get("description", "")
        row.input_schema_json = json.dumps(definition.get("parameters", {}), ensure_ascii=False)
        row.provider_type = "builtin"
        row.read_only = name != "lock_appointment_slot"
        row.requires_confirmation = name == "lock_appointment_slot"
        row.enabled = True
        tools_by_name[name] = row
    await db.flush()

    skills = (await db.execute(select(SkillPackage))).scalars().all()
    for skill in skills:
        if skill.skill_id in SKILL_CHAT_EXAMPLES:
            skill.trigger_examples = json.dumps(SKILL_CHAT_EXAMPLES[skill.skill_id], ensure_ascii=False)
        if skill.mcp_server:
            server = (await db.execute(select(MCPServerConfig).where(
                MCPServerConfig.url == skill.mcp_server
            ))).scalars().first()
            if server is None:
                server_key = re.sub(r"[^a-zA-Z0-9_-]", "-", skill.skill_id)[:120] or "mcp-server"
                if (await db.execute(select(MCPServerConfig.id).where(
                    MCPServerConfig.server_key == server_key
                ))).scalar_one_or_none():
                    server_key = f"{server_key}-server"
                server = MCPServerConfig(
                    server_key=server_key, name=_clean_server_name(skill.name), url=skill.mcp_server,
                    transport="http", health_status="unknown",
                )
                db.add(server)
                await db.flush()
            server_key = server.server_key
            for legacy_tool in json.loads(skill.tools or "[]"):
                if not isinstance(legacy_tool, dict) or not legacy_tool.get("name"):
                    continue
                original_name = legacy_tool["name"]
                tool_key = f"mcp:{server_key}:{original_name}"
                tool = (await db.execute(select(ToolDefinition).where(
                    ToolDefinition.tool_key == tool_key
                ))).scalar_one_or_none()
                if tool is None:
                    tool = ToolDefinition(tool_key=tool_key, name=f"{server_key}__{original_name}")
                    db.add(tool)
                tool.namespace = server_key
                tool.description = legacy_tool.get("description", "")
                tool.input_schema_json = json.dumps(legacy_tool.get("parameters", {}), ensure_ascii=False)
                tool.provider_type = "mcp"
                tool.provider_id = server.id
                tool.read_only = False
                tool.requires_confirmation = True
                await db.flush()
                exists = (await db.execute(select(SkillToolBinding.id).where(
                    SkillToolBinding.skill_id == skill.id,
                    SkillToolBinding.tool_id == tool.id,
                ))).scalar_one_or_none()
                if not exists:
                    db.add(SkillToolBinding(skill_id=skill.id, tool_id=tool.id, required=True))
            # Complete the compatibility migration: the Skill keeps its
            # procedure metadata and bindings, while transport ownership moves
            # to MCPServerConfig. Clearing legacy fields prevents deleted
            # servers from being recreated on every restart.
            skill.mcp_server = ""
            skill.tools = "[]"
            skill.source_type = "manual"
        manifest = json.loads(skill.manifest_json or "{}")
        allowed = tuple(manifest.get("allowed_tools") or DEFAULT_BINDINGS.get(skill.skill_id, ()))
        for tool_name in allowed:
            tool = tools_by_name.get(tool_name)
            if not tool:
                continue
            exists = (await db.execute(select(SkillToolBinding.id).where(
                SkillToolBinding.skill_id == skill.id,
                SkillToolBinding.tool_id == tool.id,
            ))).scalar_one_or_none()
            if not exists:
                db.add(SkillToolBinding(skill_id=skill.id, tool_id=tool.id, required=True))
        for agent_name in manifest.get("agents") or ():
            exists = (await db.execute(select(AgentSkillPolicy.id).where(
                AgentSkillPolicy.agent_name == agent_name,
                AgentSkillPolicy.skill_id == skill.id,
            ))).scalar_one_or_none()
            if not exists:
                db.add(AgentSkillPolicy(agent_name=agent_name, skill_id=skill.id, enabled=True))
    await _normalize_mcp_servers(db)
    mcp_tools = (await db.execute(select(ToolDefinition).where(
        ToolDefinition.provider_type == "mcp"
    ))).scalars().all()
    for tool in mcp_tools:
        tool.read_only, tool.requires_confirmation = classify_tool(
            tool.name, json.loads(tool.annotations_json or "{}")
        )
    await db.flush()
