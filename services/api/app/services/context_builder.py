"""统一上下文构建器：并行查询技能、凭证、检验、体征，组装问诊上下文。

消除 send_message / send_message_stream 中 ~60 行重复的上下文拼接逻辑。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    LabReport,
    MemoryFact,
    AgentSkillPolicy,
    MCPServerConfig,
    SkillPackage,
    SkillToolBinding,
    ToolDefinition,
    UserOAuthCredential,
    VitalStreamEvent,
)

logger = logging.getLogger(__name__)


def select_relevant_skills(
    skills: list[dict], user_text: str, agent_name: str | None = None, limit: int = 4,
) -> list[dict]:
    """Select a small Skill set; load full instructions only for selected Skills."""
    query = user_text.casefold()
    ranked: list[tuple[int, dict]] = []
    for skill in skills:
        allowed_agents = skill.get("agents") or []
        if agent_name and allowed_agents and agent_name not in allowed_agents:
            continue
        terms = [skill.get("skill_id", ""), skill.get("name", ""), skill.get("description", "")]
        terms += skill.get("keywords", []) + skill.get("trigger_examples", [])
        terms += [tool.get("name", "") for tool in skill.get("tools", []) if isinstance(tool, dict)]
        score = sum(3 if str(term).casefold() in query else 0 for term in terms if len(str(term).strip()) >= 2)
        for token in ("药", "冲突", "挂号", "预约", "文献", "研究", "pmid", "pubmed"):
            if token in query and token in " ".join(map(str, terms)).casefold():
                score += 2
        if score:
            ranked.append((score, skill))
    ranked.sort(key=lambda item: (-item[0], item[1].get("skill_id", "")))
    return [skill for _, skill in ranked[:limit]]


def _original_tool_name(name: str) -> str:
    return name.split("__", 1)[-1]


def select_relevant_tools(skill: dict, user_text: str, limit: int = 2) -> list[dict]:
    """Select only the tool schemas needed for this turn."""
    tools = skill.get("tools", [])
    if not tools:
        return []
    query = user_text.casefold()
    skill_id = skill.get("skill_id", "")
    preferred: list[str] = []
    if skill_id == "medical-literature-review":
        if "全文" in query:
            preferred = ["pubmed_fetch_fulltext"]
        elif "mesh" in query or "主题词" in query:
            preferred = ["pubmed_lookup_mesh"]
        elif "引用格式" in query:
            preferred = ["pubmed_format_citations"]
        elif "相关文献" in query or "被引" in query:
            preferred = ["pubmed_find_related"]
        elif "摘要" in query and "pmid" in query:
            preferred = ["pubmed_fetch_articles"]
        else:
            preferred = ["pubmed_search_articles", "pubmed_fetch_articles"]
    elif skill_id == "drug-safety":
        if any(word in query for word in ("药品档案", "适应症", "警告信息", "drug profile")):
            preferred = ["openfda_drug_profile"]
        elif "不良" in query:
            preferred = ["openfda_search_adverse_events"]
        elif "短缺" in query:
            preferred = ["openfda_search_drug_shortages"]
        elif "召回" in query:
            preferred = ["openfda_search_recalls", "openfda_search_enforcement"]
        elif "标签" in query or "说明书" in query:
            preferred = ["openfda_get_drug_label"]
        else:
            preferred = ["openfda_search_adverse_events", "openfda_get_drug_label"]
    elif skill_id == "healthcare-queue-simulator":
        preferred = ["recommend_md_count"] if any(word in query for word in ("多少", "几名", "配置", "需要")) else ["simulate_ed_demo"]
    elif skill_id == "healthcare-provider-directory":
        preferred = ["match_practice"] if any(word in query for word in ("推荐", "匹配", "适合")) else ["search_providers"]
    elif skill_id == "appointment-booking":
        preferred = ["lock_appointment_slot"] if any(word in query for word in ("锁号", "确认预约")) else ["query_doctor_schedule"]

    selected = [tool for suffix in preferred for tool in tools if _original_tool_name(tool.get("name", "")) == suffix]
    if selected:
        return selected[:limit]
    return tools[:limit]


@dataclass
class ConsultationContext:
    """组装好的问诊上下文。"""
    user_text: str
    user_content: str | list[dict]  # str 或多模态内容列表
    active_skills: list[dict]
    latest_report: object | None = None
    latest_vital: object | None = None


async def build_consultation_context(
    *,
    db: AsyncSession,
    user_id: str,
    body_content: str | list,
    body_media_urls: list[str] | None = None,
) -> ConsultationContext:
    """并行查询上下文数据，组装为问诊可用的结构。

    Args:
        db: 数据库会话
        user_id: 当前用户 ID
        body_content: 请求中的 content（str 或多模态 ContentPart 列表）
        body_media_urls: 已上传的媒体 URL 列表

    Returns:
        ConsultationContext 包含处理后的 user_text、user_content 和 active_skills
    """
    is_multimodal = isinstance(body_content, list)

    # 提取纯文本
    if is_multimodal:
        text_parts = [p.text for p in body_content if hasattr(p, "type") and p.type == "text" and p.text]
        user_text = " ".join(text_parts)
    else:
        user_text = str(body_content)

    # AsyncSession/asyncpg 不支持在同一连接上并行 execute，按序查询避免
    # "another operation is in progress"。
    skill_result = await db.execute(select(SkillPackage).where(SkillPackage.status == "ACTIVE"))
    cred_result = await db.execute(select(UserOAuthCredential).where(UserOAuthCredential.user_id == user_id))
    latest_report_res = await db.execute(
        select(LabReport).where(LabReport.user_id == user_id).order_by(LabReport.created_at.desc())
    )
    latest_vital_res = await db.execute(
        select(VitalStreamEvent)
        .where(VitalStreamEvent.user_id == user_id)
        .order_by(VitalStreamEvent.created_at.desc())
    )
    memory_result = await db.execute(
        select(MemoryFact)
        .where(MemoryFact.user_id == user_id, MemoryFact.status == "confirmed")
        .order_by(MemoryFact.confidence.desc())
        .limit(20)
    )
    binding_result = await db.execute(
        select(SkillToolBinding.skill_id, ToolDefinition, MCPServerConfig)
        .join(ToolDefinition, ToolDefinition.id == SkillToolBinding.tool_id)
        .outerjoin(MCPServerConfig, MCPServerConfig.id == ToolDefinition.provider_id)
        .where(ToolDefinition.enabled == True)
    )
    policy_result = await db.execute(select(AgentSkillPolicy).where(AgentSkillPolicy.enabled == True))
    skill_rows = skill_result.scalars().all()
    connected_providers = {c.provider for c in cred_result.scalars().all()}

    tools_by_skill: dict[str, list[dict]] = {}
    for skill_db_id, tool, server in binding_result.all():
        tools_by_skill.setdefault(skill_db_id, []).append({
            "id": tool.id, "name": tool.name, "description": tool.description,
            "parameters": json.loads(tool.input_schema_json or "{}"),
            "provider_type": tool.provider_type, "provider_id": tool.provider_id,
            "read_only": tool.read_only, "requires_confirmation": tool.requires_confirmation,
            "provider": ({
                "server_key": server.server_key, "transport": server.transport,
                "url": server.url, "headers": json.loads(server.headers_json or "{}"),
                "enabled": server.enabled,
            } if server else None),
        })
    agents_by_skill: dict[str, list[str]] = {}
    for policy in policy_result.scalars().all():
        agents_by_skill.setdefault(policy.skill_id, []).append(policy.agent_name)

    active_skills = [
        {
            "skill_id": s.skill_id,
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "trigger_examples": json.loads(s.trigger_examples or "[]"),
            "confirm_required": s.confirm_required,
            "tools": tools_by_skill.get(s.id, []),
            "source_type": s.source_type,
            "source_scope": s.source_scope,
            "instructions": s.instructions,
            "keywords": json.loads(s.keywords or "[]"),
            "agents": agents_by_skill.get(s.id, json.loads(s.manifest_json or "{}").get("agents", [])),
        }
        for s in skill_rows
        if (
            s.source_type != "plugin"
            or json.loads(s.manifest_json or "{}").get("auth_type", "none") == "none"
            or json.loads(s.manifest_json or "{}").get("provider") in connected_providers
        )
    ]

    latest_report = latest_report_res.scalars().first()
    latest_vital = latest_vital_res.scalars().first()

    # 已确认的长期记忆
    memory_facts = memory_result.scalars().all()
    memory_context = ""
    if memory_facts:
        memory_lines = []
        for f in memory_facts:
            try:
                val = json.loads(f.value_json)
                text = val.get("text", str(val))
            except Exception:
                text = f.value_json
            memory_lines.append(f"- [{f.fact_type}] {text}")
        memory_context = "\n[用户长期记忆]\n" + "\n".join(memory_lines)

    # 技能选择必须只看本轮用户原文，不能让长期记忆/检验摘要中的词污染工具路由。
    routing_text = user_text

    # 构建上下文后缀
    context_suffix = memory_context
    if latest_report and latest_report.summary:
        context_suffix += f"\n[最近检验摘要] {latest_report.summary}"
    if latest_vital:
        context_suffix += (
            f"\n[最近穿戴设备数据] {latest_vital.metric}={latest_vital.value}{latest_vital.unit} "
            f"risk={latest_vital.risk_level}"
        )

    # 注入上下文
    if is_multimodal:
        multimodal_content = []
        for part in body_content:
            if hasattr(part, "type"):
                if part.type == "text":
                    multimodal_content.append({"type": "text", "text": part.text or ""})
                elif part.type == "image_url" and part.image_url:
                    multimodal_content.append({"type": "image_url", "image_url": part.image_url})
                elif part.type == "video_url" and part.video_url:
                    multimodal_content.append({"type": "video_url", "video_url": part.video_url})
            elif isinstance(part, dict):
                multimodal_content.append(part)
        if body_media_urls:
            for url in body_media_urls:
                if any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    multimodal_content.append({"type": "image_url", "image_url": {"url": url}})
                elif any(ext in url.lower() for ext in [".mp4", ".avi", ".mov", ".mkv", ".webm"]):
                    multimodal_content.append({"type": "video_url", "video_url": {"url": url}})
        if context_suffix:
            multimodal_content.append({"type": "text", "text": context_suffix})
        user_content = multimodal_content
    else:
        # 路由、风险判断和工具参数必须保留用户原文；增强上下文只进入模型消息。
        user_content = user_text + context_suffix

    selected_skills = select_relevant_skills(active_skills, routing_text)
    lowered_text = routing_text.casefold()
    for skill in selected_skills:
        skill["tools"] = select_relevant_tools(skill, routing_text)
        for tool in skill.get("tools", []):
            tool["user_confirmed"] = (
                "确认执行" in lowered_text and str(tool.get("name", "")).casefold() in lowered_text
            )

    return ConsultationContext(
        user_text=user_text,
        user_content=user_content,
        active_skills=selected_skills,
        latest_report=latest_report,
        latest_vital=latest_vital,
    )
