"""
LangGraph 健康问诊 Agent 状态机 — 多 Agent 版本
节点: triage → collect_symptoms → risk_check → generate_summary
状态: INIT → COLLECTING → FOLLOW_UP → RISK_ESCALATED → SUMMARY_READY → EVENT_CARD_READY → CLOSED
"""
from __future__ import annotations
import asyncio
import json
import re
import logging
from typing import Annotated, TypedDict, Literal
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
from app.core.config import get_settings
from app.core.observability import observe_agent
from app.orchestrators.agents import get_agent_prompt, get_agent_config, select_next_agent
from app.services.tool_registry import build_openai_tools, execute_tool_call
from app.services.context_manager import (
    trim_messages_to_budget,
    build_conversation_summary,
    count_message_tokens,
)
from app.schemas.llm_output import validate_and_clean_summary

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── System Prompts (legacy fallback) ───────────────────────────────────────

CONSULTATION_SYSTEM_PROMPT = """你是一个专业的健康问诊 AI 助手，遵循以下严格原则：

【问诊原则】
1. 使用分阶段问诊流程：主诉采集 → 症状结构化 → 风险识别 → 候选方向 → 结论输出
2. 每轮只提出 1-2 个最高价值的追问，不堆叠大量问题
3. 优先识别高风险信号，再追求信息完整性
4. 遇到急重症信号（胸痛、突发剧烈头痛、呼吸困难、意识改变等）立即抬升分诊级别并建议急诊
【关于用户上传的健康档案文档】
- 若对话中含有 [已上传健康档案] 标记，表示用户已提供了历史健康文档，请从中识别关键医疗信息
- 在生成阶段性结论 JSON 时，不要将文档原文复制到任何字段中
- confirmed_points、symptom_summary、candidate_conditions 等字段应为本次对话的临床发现与分析结论，用简洁医疗术语描述，而非摘抄文档原文
【输出约束】
- 不输出"已确诊"等确诊式表达
- 不输出处方级药物建议（剂量、用法）
- 只输出候选方向和阶段性判断，不替代医生诊断
- 遇到高风险必须明确说明"建议立即就医"

【阶段性结论触发条件】
- 候选方向已收敛，继续追问边际收益低
- 已识别明确风险等级
- 用户主动要求总结
- 对话轮次 ≥ 4 轮

当进入阶段性结论时，结构化输出以下 JSON（用 ```json ... ``` 包裹）：
{
  "status": "SUMMARY_READY",
  "chief_complaint": "",
  "symptom_summary": [],
  "duration": "",
  "severity": "轻度|中度|重度",
  "confirmed_points": [],
  "uncertain_points": [],
  "red_flags": [],
  "candidate_conditions": [{"name": "", "confidence": 0.0, "supporting_points": [], "against_points": []}],
  "triage_level": "observe|outpatient|urgent_visit|emergency",
  "recommended_department": "",
  "visit_preparation": [],
  "care_todos": [],
  "medication_reminder_suggestion": [],
  "followup_reminder_suggestion": [],
  "record_update_suggestion": true,
  "insurance_material_suggestion": [],
  "summary_text": "给用户看的自然语言摘要"
}"""

CONSULTATION_SYSTEM_PROMPT_EN = """You are a professional health consultation AI assistant. Follow these strict principles:

【Consultation Principles】
1. Use a phased consultation flow: Chief Complaint Collection → Symptom Structuring → Risk Identification → Candidate Directions → Conclusion Output
2. Ask only 1-2 highest-value follow-up questions per turn; do not stack multiple questions
3. Prioritize identifying high-risk signals before pursuing completeness of information
4. If acute/severe signals are detected (chest pain, sudden severe headache, difficulty breathing, altered consciousness, etc.), immediately escalate triage level and recommend emergency care

【Regarding User-Uploaded Health Records】
- If the conversation contains an [Uploaded Health Records] marker, the user has provided historical health documents — extract key medical information from them
- When generating structured conclusion JSON, do NOT copy document text into any fields
- Fields like confirmed_points, symptom_summary, candidate_conditions should contain clinical findings and analysis conclusions from this conversation, described in concise medical terminology

【Output Constraints】
- Do NOT use definitive diagnostic expressions like "confirmed diagnosis"
- Do NOT provide prescription-level medication advice (dosage, usage)
- Only output candidate directions and phased assessments — do not replace doctor diagnosis
- For high-risk situations, clearly state "Immediate medical attention recommended"

【Conclusion Trigger Conditions】
- Candidate directions have converged; further questioning has diminishing returns
- A clear risk level has been identified
- User explicitly requests a summary
- Conversation has reached ≥ 4 turns

When entering the conclusion phase, output the following JSON wrapped in ```json ... ```:
{
  "status": "SUMMARY_READY",
  "chief_complaint": "",
  "symptom_summary": [],
  "duration": "",
  "severity": "mild|moderate|severe",
  "confirmed_points": [],
  "uncertain_points": [],
  "red_flags": [],
  "candidate_conditions": [{"name": "", "confidence": 0.0, "supporting_points": [], "against_points": []}],
  "triage_level": "observe|outpatient|urgent_visit|emergency",
  "recommended_department": "",
  "visit_preparation": [],
  "care_todos": [],
  "medication_reminder_suggestion": [],
  "followup_reminder_suggestion": [],
  "record_update_suggestion": true,
  "insurance_material_suggestion": [],
  "summary_text": "Natural language summary for the user"
}"""

RISK_ESCALATION_PROMPT = """检测到可能的高风险症状信号。请立即：
1. 提升分诊级别为 urgent_visit 或 emergency
2. 建议用户立即线下就医
3. 不再继续常规问诊追问
4. 仅收集最关键信息"""

RISK_ESCALATION_PROMPT_EN = """Possible high-risk symptom signals detected. Immediately:
1. Escalate triage level to urgent_visit or emergency
2. Advise the user to seek immediate in-person medical care
3. Stop regular follow-up questioning
4. Only collect the most critical information"""

# ─── 红旗症状关键词 ──────────────────────────────────────────────────────────

RED_FLAG_KEYWORDS = [
    "胸痛", "胸闷", "胸口痛", "胸口疼", "心脏痛", "心脏疼", "心前区", "放射至左肩", "冷汗大量",
    "突发剧烈头痛", "雷击样头痛", "意识改变", "意识不清", "昏迷", "晕厥",
    "呼吸困难", "无法呼吸", "喘不过气", "喘不上气", "呼吸不了",
    "大量出血", "吐血", "便血", "大出血",
    "急性腹痛", "剧烈腹痛", "骨折", "严重外伤", "休克",
    "高烧39度", "高烧40度", "体温40", "体温超过40", "39.5度", "39.8度",
    "左肩放射", "心悸", "心脏不适",
]


def _extract_summary_json(content: str) -> dict | None:
    """Extract summary JSON from LLM response, handling nested objects robustly."""
    # Try markdown-wrapped JSON first
    match = re.search(r"```json\s*\n?", content)
    if match:
        start = match.end()
        # Find the closing ``` after the JSON block
        end_match = re.search(r"\n?\s*```", content[start:])
        if end_match:
            json_str = content[start:start + end_match.start()]
            try:
                return json.loads(json_str.strip())
            except json.JSONDecodeError:
                pass

    # Fallback: find raw JSON object with balanced braces
    brace_start = content.find("{")
    if brace_start == -1:
        return None
    depth = 0
    for i in range(brace_start, len(content)):
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(content[brace_start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def detect_red_flags(text: str) -> bool:
    """只检测用户输入中的高风险关键词，区分大小写无关但要求精确匹配词组"""
    return any(kw in text for kw in RED_FLAG_KEYWORDS)


# EHR 文档标记
_EHR_CONTENT_MARKER = "以下是上传文档中提取的内容，请结合这些信息继续问诊分析："


def _strip_ehr_body(content: str) -> str:
    """Replace raw EHR document body with a short placeholder."""
    if _EHR_CONTENT_MARKER not in content:
        return content
    before = content[: content.index(_EHR_CONTENT_MARKER)].strip()
    return before + "\n[已上传健康档案，内容已供参考]"


def _extract_text_from_content(content) -> str:
    """从消息内容中提取纯文本（支持多模态格式）。"""
    if isinstance(content, list):
        text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        return " ".join(text_parts)
    return str(content)


def _messages_contain_images(messages: list[BaseMessage]) -> bool:
    """检查消息列表中是否包含图片（多模态内容）。"""
    for msg in messages:
        if hasattr(msg, "content") and isinstance(msg.content, list):
            for part in msg.content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


# ─── LangGraph State ────────────────────────────────────────────────────────

class ConsultationState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    status: Literal[
        "INIT", "COLLECTING", "FOLLOW_UP",
        "RISK_ESCALATED", "SUMMARY_READY", "EVENT_CARD_READY", "CLOSED"
    ]
    round_count: int
    red_flag_detected: bool
    extracted_fields: dict
    summary_json: dict | None
    latest_assistant_message: str
    active_skills: list[dict]
    lang: str | None
    current_agent: str
    user_requested_summary: bool
    user_llm_config: dict | None


class OutputLimitExceeded(RuntimeError):
    """The provider still stopped for length after bounded continuation."""


# ─── LLM Factory ────────────────────────────────────────────────────────────

def get_llm(
    temperature: float | None = None,
    max_tokens: int = 1200,
    tools: list[dict] | None = None,
    model: str | None = None,
    user_api_key: str | None = None,
    user_base_url: str | None = None,
    user_model: str | None = None,
) -> ChatOpenAI:
    """Create a ChatOpenAI instance with optional tool binding.

    重试由外层 tenacity 包装统一处理，这里关闭 SDK 自带 retry 避免叠加。
    支持用户自定义 LLM 配置（优先级高于全局配置）。
    """
    llm = ChatOpenAI(
        model=user_model or model or settings.LLM_MODEL,
        temperature=temperature or settings.LLM_TEMPERATURE,
        openai_api_key=user_api_key or settings.OPENAI_API_KEY,
        openai_api_base=user_base_url or settings.OPENAI_BASE_URL,
        streaming=True,
        max_tokens=max_tokens,
        timeout=settings.LLM_REQUEST_TIMEOUT,
        max_retries=0,
    )
    if tools:
        llm = llm.bind_tools(tools)
    return llm


# ─── Helper functions ───────────────────────────────────────────────────────

def _build_skills_block(active_skills: list[dict]) -> str:
    """将活跃技能列表格式化为 System Prompt 中的技能上下文段落。"""
    if not active_skills:
        return ""
    lines = ["\n\n【已注册插件技能】"]
    for sk in active_skills:
        tools = sk.get("tools", [])
        tool_names = "、".join(t["name"] for t in tools if isinstance(t, dict)) if tools else "无"
        triggers = "；".join(sk.get("trigger_examples", [])) or "无"
        lines.append(
            f"- skill_id={sk['skill_id']} | 名称：{sk['name']} | 分类：{sk.get('category','通用')}"
            f"\n  描述：{sk.get('description','')}"
            f"\n  工具：{tool_names} | 触发场景：{triggers}"
        )
        if sk.get("instructions"):
            lines.append(f"  执行说明：{sk['instructions']}")
    lines.append(
        "\n【工具调用规则】\n"
        "你拥有可用的工具函数（tools）。当用户意图匹配以下场景时，你**必须**使用工具函数调用来执行，**禁止**自行编造结果：\n"
        "- 药物相互作用查询 → 调用 openfda-drug-safety 相关工具（如 openfda_search_adverse_events、openfda_get_drug_label 等）\n"
        "- 医学文献检索 → 调用 pubmed-research 相关工具（如 pubmed_search_articles、pubmed_fetch_articles 等）\n"
        "- 挂号/查号源/查排班 → 调用 query_doctor_schedule\n"
        "- 锁号/预约 → 调用 lock_appointment_slot\n"
        "调用工具后，**必须**根据返回结果为用户生成自然语言回复，即使工具返回错误也要告知用户。\n"
        "❌ 禁止：对工具覆盖范围内的问题直接编造答案（不调用工具）\n"
        "✅ 正确：先调用工具获取真实数据，再基于结果回复用户"
    )
    return "\n".join(lines)


def _skills_for_agent(active_skills: list[dict] | None, agent_key: str) -> list[dict]:
    """Apply per-Agent Skill allowlists before prompt and tool injection."""
    return [skill for skill in active_skills or [] if not skill.get("agents") or agent_key in skill["agents"]]


def _build_system_message(state: ConsultationState, rag_context: str = "", lang: str | None = None) -> SystemMessage:
    """Build system message for legacy single-agent fallback path."""
    from datetime import date as _date
    today_str = _date.today().strftime("%Y-%m-%d" if lang == "en" else "%Y年%m月%d日")
    is_en = lang == "en"
    if is_en:
        date_hint = f"\n\n【Current Date】Today is {today_str}."
        base = CONSULTATION_SYSTEM_PROMPT_EN + date_hint
        risk_prompt = RISK_ESCALATION_PROMPT_EN
    else:
        date_hint = f"\n\n【当前日期】今天是 {today_str}。"
        base = CONSULTATION_SYSTEM_PROMPT + date_hint
        risk_prompt = RISK_ESCALATION_PROMPT
    skills_block = _build_skills_block(state.get("active_skills") or [])
    rag_block = ""
    if rag_context:
        if is_en:
            rag_block = f"\n\n【Reference Knowledge Base Results】\n{rag_context}"
        else:
            rag_block = f"\n\n【参考知识库检索结果】\n{rag_context}"
    if state["red_flag_detected"]:
        return SystemMessage(content=base + skills_block + rag_block + "\n\n" + risk_prompt)
    return SystemMessage(content=base + skills_block + rag_block)


def _build_agent_system_message(agent_key: str, state: ConsultationState, rag_context: str = "", lang: str = "zh", include_skills: bool = True) -> SystemMessage:
    """Build system message for a specific multi-agent node."""
    from datetime import date as _date
    today_str = _date.today().strftime("%Y-%m-%d" if lang == "en" else "%Y年%m月%d日")
    is_en = lang == "en"

    # Get agent-specific prompt with variable substitution
    extracted_str = json.dumps(state.get("extracted_fields", {}), ensure_ascii=False, indent=2)

    # 用 context_manager 构建摘要：最近 10 条截取 200 字 + 历史摘要
    recent_msgs = state["messages"][-10:]
    conversation_summary = "\n".join(
        f"{m.__class__.__name__.replace('Message','')}: {str(m.content)[:200]}"
        for m in recent_msgs
    )

    # 对较长的对话，用滑动窗口摘要替代完整重放
    all_msgs = state["messages"]
    if len(all_msgs) > 12:
        history_summary = build_conversation_summary(all_msgs, max_chars=1500)
        full_conversation = f"[历史摘要]\n{history_summary}\n\n[最近对话]\n" + "\n".join(
            f"{m.__class__.__name__.replace('Message','')}: {str(m.content)}"
            for m in all_msgs[-6:]
        )
    else:
        full_conversation = "\n".join(
            f"{m.__class__.__name__.replace('Message','')}: {str(m.content)}"
            for m in all_msgs
        )

    agent_prompt = get_agent_prompt(
        agent_key, lang,
        extracted_fields=extracted_str,
        conversation_summary=conversation_summary,
        full_conversation=full_conversation,
    )

    # Add date context
    if is_en:
        date_hint = f"\n\nCurrent Date: {today_str}"
    else:
        date_hint = f"\n\n当前日期: {today_str}"

    # Add output constraints
    if is_en:
        constraints = "\n\n【Output Constraints】\n- Do NOT use definitive diagnostic expressions\n- Do NOT provide prescription-level medication advice\n- Only output candidate directions, do not replace doctor diagnosis"
    else:
        constraints = "\n\n【输出约束】\n- 不输出确诊式表达\n- 不输出处方级药物建议\n- 只输出候选方向，不替代医生诊断"

    # Add RAG context
    rag_block = ""
    if rag_context:
        if is_en:
            rag_block = f"\n\n【Reference Knowledge】\n{rag_context}"
        else:
            rag_block = f"\n\n【参考知识库】\n{rag_context}"

    # Add skills block (skip for summary agent — it only needs to produce JSON, not call tools)
    skills_block = _build_skills_block(_skills_for_agent(state.get("active_skills"), agent_key)) if include_skills else ""

    return SystemMessage(content=agent_prompt + date_hint + constraints + rag_block + skills_block)


def _get_rag_context_sync(messages: list[BaseMessage]) -> str:
    """Retrieve RAG context from the last user message (blocking)."""
    try:
        from app.services.rag_retriever import retrieve
        user_msgs = [m for m in messages if isinstance(m, HumanMessage)]
        if user_msgs:
            content = user_msgs[-1].content
            # 多模态消息：提取文本部分用于 RAG 检索
            if isinstance(content, list):
                text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                query_text = " ".join(text_parts)
            else:
                query_text = str(content)
            if query_text.strip():
                return retrieve(query_text, top_k=3)
    except Exception:
        pass
    return ""


async def _get_rag_context(messages: list[BaseMessage]) -> str:
    """Retrieve RAG context with timeout to avoid blocking on model download."""
    try:
        from app.core.concurrency import get_rag_executor
        executor = get_rag_executor()
        loop = asyncio.get_running_loop()
        text_context = await asyncio.wait_for(
            loop.run_in_executor(executor, _get_rag_context_sync, messages),
            timeout=5.0,
        )
    except (asyncio.TimeoutError, Exception):
        text_context = ""

    # 查询知识库中的图片文档，附加到上下文中
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.models.models import KnowledgeDocument
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.source_type == "image",
                ).limit(5)
            )
            image_docs = result.scalars().all()
            if image_docs:
                image_lines = []
                for doc in image_docs:
                    image_url = f"/api/v1/rag/documents/{doc.id}/image"
                    image_lines.append(f"[知识库图片] {doc.title} — 查看图片: {image_url}")
                image_context = "\n".join(image_lines)
                if text_context:
                    return f"{text_context}\n---\n{image_context}"
                return image_context
    except Exception:
        pass

    return text_context


async def _handle_tool_calls(
    response: AIMessage,
    llm_with_tools: ChatOpenAI,
    messages: list[BaseMessage],
    system_msg: SystemMessage,
    db_session=None,
    user_id: str | None = None,
    active_skills: list[dict] | None = None,
) -> tuple[str, list[BaseMessage]]:
    """Handle tool calls from LLM response. Loop until LLM returns final text.

    Returns (final_content, updated_messages).
    """
    content = ""
    current_messages = list(messages)

    # Check if response has tool_calls
    if not hasattr(response, "tool_calls") or not response.tool_calls:
        return response.content or "", current_messages

    # Process tool calls
    while response.tool_calls:
        current_messages.append(response)

        for tc in response.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool_id = tc["id"]

            logger.info(f"Executing tool call: {tool_name} with args: {tool_args}")
            result = await execute_tool_call(tool_name, tool_args, db_session, user_id, active_skills)
            current_messages.append(
                ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=tool_id)
            )

        # Re-invoke LLM with tool results
        response = await _llm_invoke_with_semaphore(llm_with_tools, [system_msg] + current_messages)
        content = response.content or ""

    # Tool-backed answers can be much longer than the short consultation-agent
    # budget. Continue only when the provider explicitly reports truncation.
    continuation_count = 0
    while _response_was_truncated(response) and continuation_count < 3:
        continuation_count += 1
        current_messages.extend([
            response,
            HumanMessage(content="继续完成上一条回答，严格满足用户要求；不要重复已经输出的内容。"),
        ])
        response = await _llm_invoke_with_semaphore(llm_with_tools, [system_msg] + current_messages)
        content += response.content or ""

    return content, current_messages


async def _handle_tool_calls_stream(
    response: AIMessage,
    llm_with_tools: ChatOpenAI,
    messages: list[BaseMessage],
    system_msg: SystemMessage,
    db_session=None,
    user_id: str | None = None,
    active_skills: list[dict] | None = None,
):
    """Handle tool calls in streaming mode. Yields tool execution events.

    Yields:
        ("tool_start", {"name": str, "args": dict})
        ("tool_end", {"name": str, "result": dict})
        ("token", str) — final LLM response tokens
    """
    current_messages = list(messages)

    if not hasattr(response, "tool_calls") or not response.tool_calls:
        if response.content:
            yield ("token", response.content)
        return

    continuation_count = 0
    while response.tool_calls:
        current_messages.append(response)

        for tc in response.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool_id = tc["id"]

            skill_meta = _resolve_tool_skill(tool_name, active_skills)
            yield ("tool_start", {"name": tool_name, "args": tool_args, "call_id": tool_id, **skill_meta})
            result = await execute_tool_call(tool_name, tool_args, db_session, user_id, active_skills)
            yield ("tool_end", {"name": tool_name, "result": result, "call_id": tool_id, **skill_meta})

            current_messages.append(
                ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=tool_id)
            )

        # Re-invoke LLM with tool results, stream the response
        from app.core.concurrency import get_llm_semaphore
        sem = get_llm_semaphore()
        await asyncio.wait_for(sem.acquire(), timeout=settings.CONCURRENCY_LLM_ACQUIRE_TIMEOUT)
        try:
            response = None
            async for chunk in llm_with_tools.astream([system_msg] + current_messages):
                if response is None:
                    response = chunk
                else:
                    response = response + chunk
                token = chunk.content
                if token:
                    yield ("token", token)
        finally:
            sem.release()

        if response and response.tool_calls:
            # LLM wants more tool calls
            continue
        elif response and _response_was_truncated(response):
            while response and _response_was_truncated(response) and continuation_count < 3:
                continuation_count += 1
                current_messages.extend([
                    response,
                    HumanMessage(content="继续完成上一条回答，严格满足用户要求；不要重复已经输出的内容。"),
                ])
                # Ask for the missing tail and append it to the same SSE answer.
                sem = get_llm_semaphore()
                await asyncio.wait_for(sem.acquire(), timeout=settings.CONCURRENCY_LLM_ACQUIRE_TIMEOUT)
                try:
                    next_response = None
                    async for chunk in llm_with_tools.astream([system_msg] + current_messages):
                        next_response = chunk if next_response is None else next_response + chunk
                        if chunk.content:
                            yield ("token", chunk.content)
                    response = next_response
                finally:
                    sem.release()
            if response and _response_was_truncated(response):
                raise OutputLimitExceeded("工具调用后的回答超出总输出上限")
            break
        else:
            break


def _response_was_truncated(response: AIMessage | None) -> bool:
    """Return True only when the model provider reports a token-limit stop."""
    if response is None:
        return False
    metadata = getattr(response, "response_metadata", {}) or {}
    finish_reason = metadata.get("finish_reason") or metadata.get("stop_reason")
    if finish_reason in ("length", "max_tokens"):
        return True
    generation_info = getattr(response, "generation_info", None) or {}
    return generation_info.get("finish_reason") in ("length", "max_tokens")


def _content_looks_truncated(content: str) -> bool:
    """Detect a small set of unambiguous broken stream endings.

    Some OpenAI-compatible providers omit finish_reason. A replacement
    character or a dangling separator at the very end is strong evidence that
    the answer ended mid-item, while ordinary sentence endings are untouched.
    """
    tail = (content or "").rstrip()
    return bool(tail) and tail.endswith(("�", "—", "：", ":", "（", "("))


def _resolve_tool_skill(tool_name: str, active_skills: list[dict] | None) -> dict[str, str]:
    for skill in active_skills or []:
        if any(t.get("name") == tool_name for t in skill.get("tools", []) if isinstance(t, dict)):
            return {"skill_id": skill.get("skill_id", ""), "skill_name": skill.get("name", tool_name)}
    builtin_names = {
        "check_drug_interaction": ("drug-safety", "用药安全检查"),
        "query_doctor_schedule": ("appointment-booking", "挂号预约"),
        "lock_appointment_slot": ("appointment-booking", "挂号预约"),
    }
    skill_id, skill_name = builtin_names.get(tool_name, (tool_name, tool_name))
    return {"skill_id": skill_id, "skill_name": skill_name}


# ─── LLM Semaphore Helper ─────────────────────────────────────────────────

async def _llm_invoke_with_semaphore(llm, messages) -> AIMessage:
    """Call LLM with semaphore-gated concurrency + tenacity retry."""
    from app.core.concurrency import get_llm_semaphore
    from app.core.retry import llm_retry

    sem = get_llm_semaphore()

    async for attempt in llm_retry():
        with attempt:
            try:
                await asyncio.wait_for(sem.acquire(), timeout=settings.CONCURRENCY_LLM_ACQUIRE_TIMEOUT)
            except asyncio.TimeoutError:
                from fastapi import HTTPException
                raise HTTPException(status_code=503, detail="AI 服务繁忙，请稍后重试")
            try:
                return await llm.ainvoke(messages)
            finally:
                sem.release()


# ─── Multi-Agent Nodes ──────────────────────────────────────────────────────

async def _run_agent_with_tools(
    state: ConsultationState,
    system_msg: SystemMessage,
    temperature: float,
    max_tokens: int,
    user_llm_config: dict | None = None,
    agent_key: str = "collector",
) -> str:
    """Run an agent with native tool calling. Loops until LLM returns plain text."""
    selected_skills = _skills_for_agent(state.get("active_skills"), agent_key)
    tools = build_openai_tools(selected_skills)
    # 检查是否包含图片，使用支持多模态的模型
    has_images = _messages_contain_images(state["messages"])
    model = settings.MIMO_OMNI_MODEL if has_images else None
    ucfg = user_llm_config or {}
    llm = get_llm(temperature=temperature, max_tokens=max_tokens, tools=tools if tools else None, model=model,
                  user_api_key=ucfg.get("api_key"), user_base_url=ucfg.get("base_url"), user_model=ucfg.get("model"))

    # Token 级裁剪：将消息裁剪到预算内，避免超出上下文窗口
    trimmed_messages = trim_messages_to_budget(list(state["messages"]))
    messages_with_system = [system_msg] + trimmed_messages

    token_count = count_message_tokens(trimmed_messages)
    if token_count > settings.MEMORY_TOKEN_BUDGET:
        logger.info(f"消息裁剪: {len(state['messages'])} → {len(trimmed_messages)} 条, ~{token_count} tokens")

    response = await _llm_invoke_with_semaphore(llm, messages_with_system)
    content: str = response.content or ""

    if hasattr(response, "tool_calls") and response.tool_calls:
        content, _ = await _handle_tool_calls(
            response, llm, list(state["messages"]), system_msg,
            active_skills=selected_skills,
        )

    return content


@observe_agent("triage")
async def triage_node(state: ConsultationState) -> ConsultationState:
    """Initial triage: assess chief complaint, detect emergencies, suggest department."""
    lang = state.get("lang") or "zh"
    rag_context = await _get_rag_context(state["messages"])

    # 知识图谱上下文注入
    kg_context = ""
    try:
        from app.services.kg_service import get_context_summary
        user_text = " ".join(
            _extract_text_from_content(m.content) for m in state["messages"]
            if hasattr(m, "content") and isinstance(m, HumanMessage)
        )
        # 简单分词提取症状关键词
        import re as _re
        keywords = [w for w in _re.split(r'[，,、。\s]+', user_text) if 2 <= len(w) <= 6]
        if keywords:
            kg_context = get_context_summary(keywords[:8])
    except Exception:
        pass

    system_msg = _build_agent_system_message("triage", state, rag_context + kg_context, lang)

    config = get_agent_config("triage")
    content = await _run_agent_with_tools(state, system_msg, config["temperature"], config["max_tokens"],
                                          user_llm_config=state.get("user_llm_config"), agent_key="triage")

    user_text = " ".join(
        _extract_text_from_content(m.content) for m in state["messages"]
        if hasattr(m, "content") and isinstance(m, HumanMessage)
    )
    red_flag = detect_red_flags(user_text)
    new_status = "RISK_ESCALATED" if red_flag else "COLLECTING"

    return {
        **state,
        "messages": [AIMessage(content=content)],
        "status": new_status,
        "round_count": state["round_count"] + 1,
        "red_flag_detected": red_flag,
        "latest_assistant_message": content,
        "current_agent": "triage",
    }


@observe_agent("collector")
async def symptom_collector_node(state: ConsultationState) -> ConsultationState:
    """Collect symptom details through targeted follow-up questions."""
    lang = state.get("lang") or "zh"
    rag_context = await _get_rag_context(state["messages"])
    system_msg = _build_agent_system_message("collector", state, rag_context, lang)

    config = get_agent_config("collector")
    content = await _run_agent_with_tools(state, system_msg, config["temperature"], config["max_tokens"],
                                          user_llm_config=state.get("user_llm_config"), agent_key="collector")

    user_text = " ".join(
        _extract_text_from_content(m.content) for m in state["messages"]
        if hasattr(m, "content") and isinstance(m, HumanMessage)
    )
    red_flag = detect_red_flags(user_text)

    new_status = state["status"]
    if red_flag:
        new_status = "RISK_ESCALATED"
    elif state["round_count"] >= 2 and new_status == "COLLECTING":
        new_status = "FOLLOW_UP"

    return {
        **state,
        "messages": [AIMessage(content=content)],
        "status": new_status,
        "round_count": state["round_count"] + 1,
        "red_flag_detected": red_flag,
        "latest_assistant_message": content,
        "current_agent": "collector",
    }


@observe_agent("risk")
async def risk_assessor_node(state: ConsultationState) -> ConsultationState:
    """Evaluate risk level based on collected symptoms."""
    lang = state.get("lang") or "zh"
    rag_context = await _get_rag_context(state["messages"])
    system_msg = _build_agent_system_message("risk", state, rag_context, lang)

    config = get_agent_config("risk")
    content = await _run_agent_with_tools(state, system_msg, config["temperature"], config["max_tokens"],
                                          user_llm_config=state.get("user_llm_config"), agent_key="risk")

    return {
        **state,
        "messages": [AIMessage(content=content)],
        "status": "RISK_ESCALATED",
        "round_count": state["round_count"] + 1,
        "red_flag_detected": True,
        "latest_assistant_message": content,
        "current_agent": "risk",
    }


@observe_agent("summary")
async def summary_generator_node(state: ConsultationState) -> ConsultationState:
    """Generate structured health event card from complete conversation.

    NOTE: This node intentionally does NOT bind tools — the summary agent
    only needs to produce a JSON block, and binding tools causes the LLM
    to prefer tool_calls over JSON output.
    """
    lang = state.get("lang") or "zh"

    # 知识图谱上下文注入
    kg_context = ""
    try:
        from app.services.kg_service import get_context_summary
        extracted = state.get("extracted_fields") or {}
        symptoms = extracted.get("symptom_summary") or []
        diseases = [c.get("name", "") for c in (extracted.get("candidate_conditions") or []) if c.get("name")]
        if symptoms or diseases:
            kg_context = get_context_summary(symptoms, diseases)
    except Exception:
        pass

    system_msg = _build_agent_system_message("summary", state, kg_context, lang, include_skills=False)

    agent_config = get_agent_config("summary")
    # 检查是否包含图片，使用支持多模态的模型
    has_images = _messages_contain_images(state["messages"])
    model = settings.MIMO_OMNI_MODEL if has_images else None
    ucfg = state.get("user_llm_config") or {}
    llm = get_llm(temperature=agent_config["temperature"], max_tokens=agent_config["max_tokens"], model=model,
                  user_api_key=ucfg.get("api_key"), user_base_url=ucfg.get("base_url"), user_model=ucfg.get("model"))

    # Token 级裁剪：长对话避免超出上下文窗口
    trimmed_messages = trim_messages_to_budget(list(state["messages"]))
    messages_with_system = [system_msg] + trimmed_messages

    response = await _llm_invoke_with_semaphore(llm, messages_with_system)
    content: str = response.content or ""

    summary_json: dict | None = None
    new_status = state["status"]
    parsed = _extract_summary_json(content)
    min_rounds = 2 if state.get("user_requested_summary") else 3
    if parsed and state["round_count"] >= min_rounds:
        # Pydantic 校验 LLM 输出
        validated = validate_and_clean_summary(parsed)
        if validated:
            summary_json = validated
            new_status = "SUMMARY_READY"
        else:
            logger.warning(f"Summary JSON 校验失败，原始输出: {str(parsed)[:300]}")
            # 校验失败但有原始数据，保留所有字段并补全必需默认值
            summary_json = {
                "status": "SUMMARY_READY",
                "chief_complaint": str(parsed.get("chief_complaint", "")),
                "summary_text": str(parsed.get("summary_text", "")),
                "triage_level": parsed.get("triage_level", "observe"),
                "severity": parsed.get("severity", "中度"),
            }
            # 保留原始数据中的所有其他字段
            for key, val in parsed.items():
                if key not in summary_json:
                    summary_json[key] = val
            new_status = "SUMMARY_READY"

    return {
        **state,
        "messages": [AIMessage(content=content)],
        "status": new_status,
        "round_count": state["round_count"] + 1,
        "red_flag_detected": state["red_flag_detected"],
        "summary_json": summary_json,
        "latest_assistant_message": content,
        "current_agent": "summary",
    }


# ─── Routing Logic ──────────────────────────────────────────────────────────

def route_next(state: ConsultationState) -> str:
    """Route to the next agent node based on current state."""
    next_agent = select_next_agent(
        round_count=state["round_count"],
        status=state["status"],
        red_flag_detected=state["red_flag_detected"],
        extracted_fields=state.get("extracted_fields", {}),
        lang=state.get("lang") or "zh",
        user_requested_summary=state.get("user_requested_summary", False),
    )
    return next_agent


def should_continue(state: ConsultationState) -> str:
    """Decide whether to continue to next agent or end."""
    if state["status"] in ("SUMMARY_READY", "EVENT_CARD_READY", "CLOSED", "RISK_ESCALATED"):
        return END
    if state["round_count"] >= 8:
        return END
    return "route"


# ─── Build Multi-Agent Graph ────────────────────────────────────────────────

def _build_graph_builder() -> StateGraph:
    """构建 graph builder（不含 compile，便于注入 checkpointer）。"""
    builder = StateGraph(ConsultationState)

    # Add agent nodes (all with native tool calling)
    builder.add_node("triage", triage_node)
    builder.add_node("collector", symptom_collector_node)
    builder.add_node("risk", risk_assessor_node)
    builder.add_node("summary", summary_generator_node)
    builder.add_node("route", lambda state: state)  # pass-through for routing

    # Entry: go to routing first
    builder.add_edge(START, "route")

    # Conditional routing from route node
    builder.add_conditional_edges(
        "route",
        route_next,
        {
            "triage": "triage",
            "collector": "collector",
            "risk": "risk",
            "summary": "summary",
        },
    )

    # After each agent, check if we should continue or end
    for agent_node in ["triage", "collector", "risk", "summary"]:
        builder.add_conditional_edges(agent_node, should_continue, {"route": "route", END: END})

    return builder


def build_consultation_graph():
    """Build the multi-agent LangGraph (无 checkpointer，向后兼容）。"""
    return _build_graph_builder().compile()


# 全局 graph 实例（无 checkpointer，用于向后兼容）
consultation_graph = build_consultation_graph()


async def build_consultation_graph_with_checkpoint():
    """Build the multi-agent LangGraph with PostgreSQL checkpointer."""
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        checkpointer = AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL)
        builder = _build_graph_builder()
        return builder.compile(checkpointer=checkpointer)
    except Exception as e:
        logger.warning(f"PostgreSQL checkpointer 初始化失败，回退到无 checkpointer 模式: {e}")
        return build_consultation_graph()


# ─── Public Interface ───────────────────────────────────────────────────────

async def run_consultation_turn(
    session_id: str,
    messages: list[dict],
    current_status: str = "INIT",
    round_count: int = 0,
    active_skills: list[dict] | None = None,
    lang: str | None = None,
    existing_extracted_fields: dict | None = None,
    use_checkpoint: bool = False,
    user_llm_config: dict | None = None,
) -> ConsultationState:
    """运行一轮问诊（多 Agent 版本），返回更新后的状态。

    Args:
        use_checkpoint: 若为 True，使用 PostgreSQL checkpointer 持久化会话状态，
            可在进程重启后恢复。默认 False 以保持向后兼容。
    """
    from app.services.context_manager import cache_session_state

    lc_messages: list[BaseMessage] = []
    for m in messages:
        if m["role"] == "user":
            content = m["content"]
            # 多模态消息：content 为列表时，直接使用 OpenAI Vision 格式
            if isinstance(content, list):
                lc_messages.append(HumanMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=_strip_ehr_body(content)))
        elif m["role"] == "assistant":
            lc_messages.append(AIMessage(content=m["content"]))

    # Detect if user explicitly requested summary
    _summary_keywords = ["总结", "结论", "阶段性", "summary", "conclude"]
    last_user_content = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    last_user_msg = _extract_text_from_content(last_user_content)
    user_requested_summary = any(kw in last_user_msg for kw in _summary_keywords)

    initial_state: ConsultationState = {
        "messages": lc_messages,
        "session_id": session_id,
        "status": current_status,
        "round_count": round_count,
        "red_flag_detected": False,
        "extracted_fields": existing_extracted_fields or {},
        "summary_json": None,
        "latest_assistant_message": "",
        "active_skills": active_skills or [],
        "lang": lang,
        "current_agent": "",
        "user_requested_summary": user_requested_summary,
        "user_llm_config": user_llm_config,
    }

    # 选择 graph：带 checkpointer 或不带
    if use_checkpoint:
        graph = await build_consultation_graph_with_checkpoint()
        result = await graph.ainvoke(initial_state, config={"configurable": {"thread_id": session_id}})
    else:
        result = await consultation_graph.ainvoke(initial_state)

    # 缓存状态到 Redis（异步，不阻塞返回）
    try:
        cacheable = {
            "session_id": session_id,
            "status": result.get("status"),
            "round_count": result.get("round_count"),
            "red_flag_detected": result.get("red_flag_detected"),
            "extracted_fields": result.get("extracted_fields"),
            "current_agent": result.get("current_agent"),
        }
        await cache_session_state(session_id, cacheable)
    except Exception:
        pass  # 缓存失败不影响主流程

    return result


async def cleanup_checkpoint(session_id: str) -> None:
    """删除会话时同步删除 PostgreSQL checkpoint 数据。"""
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        checkpointer = AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL)
        # 删除该 thread_id 的所有 checkpoint
        async with checkpointer.conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM checkpoint_blobs WHERE thread_id = %s", (session_id,)
            )
            await cur.execute(
                "DELETE FROM checkpoints WHERE thread_id = %s", (session_id,)
            )
            await checkpointer.conn.commit()
        logger.info(f"已清理会话 {session_id} 的 checkpoint 数据")
    except Exception as e:
        logger.warning(f"清理 checkpoint 失败（不影响主流程）: {e}")


async def run_consultation_turn_stream(
    session_id: str,
    messages: list[dict],
    current_status: str = "INIT",
    round_count: int = 0,
    active_skills: list[dict] | None = None,
    lang: str | None = None,
    existing_extracted_fields: dict | None = None,
    user_llm_config: dict | None = None,
    db_session=None,
    user_id: str | None = None,
):
    """流式运行一轮问诊（多 Agent 版本）。

    First determines which agent to run, then streams that agent's output.
    Supports native tool calling in streaming mode.

    Yields:
        ("token", str) — LLM output tokens
        ("tool_start", dict) — tool execution started
        ("tool_end", dict) — tool execution completed
        ("state", ConsultationState) — final state
    """
    lc_messages: list[BaseMessage] = []
    for m in messages:
        if m["role"] == "user":
            content = m["content"]
            # 多模态消息：content 为列表时，直接使用 OpenAI Vision 格式
            if isinstance(content, list):
                lc_messages.append(HumanMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=_strip_ehr_body(content)))
        elif m["role"] == "assistant":
            lc_messages.append(AIMessage(content=m["content"]))

    # Determine which agent to run
    # Detect if user explicitly requested summary
    _summary_keywords = ["总结", "结论", "阶段性", "summary", "conclude"]
    last_user_content = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    last_user_msg = last_user_content if isinstance(last_user_content, str) else str(last_user_content)
    user_requested_summary = any(kw in last_user_msg for kw in _summary_keywords)

    next_agent = select_next_agent(
        round_count=round_count,
        status=current_status,
        red_flag_detected=False,
        extracted_fields={},
        lang=lang or "zh",
        user_requested_summary=user_requested_summary,
    )

    _lang = lang or "zh"
    rag_context = await _get_rag_context(lc_messages)

    # Build system message and LLM for the selected agent
    # Summary agent does NOT get tools — it only produces JSON
    is_summary = next_agent == "summary"
    selected_skills = _skills_for_agent(active_skills, next_agent)
    system_msg = _build_agent_system_message(next_agent, {
        "messages": lc_messages,
        "active_skills": selected_skills,
        "extracted_fields": existing_extracted_fields or {},
        "red_flag_detected": False,
    }, rag_context, _lang, include_skills=not is_summary)
    config = get_agent_config(next_agent)
    tools = build_openai_tools(selected_skills) if not is_summary else []
    # 检查是否包含图片，使用支持多模态的模型
    has_images = _messages_contain_images(lc_messages)
    model = settings.MIMO_OMNI_MODEL if has_images else None
    ucfg = user_llm_config or {}
    llm = get_llm(temperature=config["temperature"], max_tokens=config["max_tokens"], tools=tools if tools else None, model=model,
                  user_api_key=ucfg.get("api_key"), user_base_url=ucfg.get("base_url"), user_model=ucfg.get("model"))

    # Token 级裁剪
    fixed_tokens = count_message_tokens([system_msg])
    input_budget = max(500, settings.MEMORY_TOKEN_BUDGET - fixed_tokens - config["max_tokens"] // 4)
    trimmed_messages = trim_messages_to_budget(lc_messages, token_budget=input_budget)
    messages_with_system = [system_msg] + trimmed_messages

    # Stream LLM response. Unlike ainvoke(), astream() does not pass through
    # _llm_invoke_with_semaphore, so retries must be applied explicitly here.
    # Retrying is safe only before any visible token has been emitted; after
    # that point a retry would duplicate text in the client.
    from app.core.concurrency import get_llm_semaphore
    from app.core.retry import EmptyLLMResponseError, llm_retry
    sem = get_llm_semaphore()
    full_content = ""
    response_obj = None
    try:
        # Two streaming attempts are enough to absorb a transient disconnect.
        # If both fail before the first token, fall back to the more compatible
        # non-streaming endpoint below instead of returning an empty bubble.
        async for attempt in llm_retry(max_attempts=1):
            with attempt:
                attempt_content = ""
                attempt_response = None
                acquired = False
                try:
                    await asyncio.wait_for(
                        sem.acquire(), timeout=settings.CONCURRENCY_LLM_ACQUIRE_TIMEOUT
                    )
                    acquired = True
                    async for chunk in llm.astream(messages_with_system):
                        attempt_response = chunk if attempt_response is None else attempt_response + chunk
                        token = chunk.content
                        if token:
                            attempt_content += token
                            full_content += token
                            yield ("token", token)
                except Exception as exc:
                    if attempt_content:
                        raise RuntimeError("AI 流式响应中断，请重试本条消息") from exc
                    raise
                finally:
                    if acquired:
                        sem.release()

                has_attempt_tool_calls = (
                    attempt_response
                    and getattr(attempt_response, "tool_calls", None)
                )
                if not attempt_content.strip() and not has_attempt_tool_calls:
                    raise EmptyLLMResponseError("AI 模型返回空响应")
                response_obj = attempt_response
            break
    except Exception:
        if full_content:
            raise
        logger.warning("流式 LLM 调用失败，切换到非流式兼容模式", exc_info=True)
        response_obj = await _llm_invoke_with_semaphore(llm, messages_with_system)
        fallback_content = response_obj.content or ""
        if fallback_content:
            full_content = fallback_content
            yield ("token", fallback_content)

    # Handle tool calls if present
    has_tool_calls = response_obj and hasattr(response_obj, "tool_calls") and response_obj.tool_calls
    if has_tool_calls:
        async for event_type, payload in _handle_tool_calls_stream(
            response_obj, llm, lc_messages, system_msg,
            db_session=db_session,
            user_id=user_id,
            active_skills=selected_skills,
        ):
            if event_type == "token":
                full_content += payload
            yield (event_type, payload)
    else:
        # The tool-call streaming path already handles token-limit
        # continuation. Apply the same behavior to ordinary consultation
        # answers; previously these were incorrectly persisted as completed.
        continuation_count = 0
        continuation_messages = list(messages_with_system)
        while (
            (_response_was_truncated(response_obj) or _content_looks_truncated(full_content))
            and continuation_count < 3
        ):
            continuation_count += 1
            if full_content.rstrip().endswith("�"):
                full_content = full_content.rstrip()[:-1]
            continuation_messages.extend([
                response_obj or AIMessage(content=full_content),
                HumanMessage(content="继续完成上一条回答，不要重复已经输出的内容，从中断处自然衔接。"),
            ])
            next_response = None
            acquired = False
            try:
                await asyncio.wait_for(
                    sem.acquire(), timeout=settings.CONCURRENCY_LLM_ACQUIRE_TIMEOUT
                )
                acquired = True
                async for chunk in llm.astream(continuation_messages):
                    next_response = chunk if next_response is None else next_response + chunk
                    if chunk.content:
                        full_content += chunk.content
                        yield ("token", chunk.content)
            finally:
                if acquired:
                    sem.release()
            if next_response is None:
                raise RuntimeError("AI 续写返回空响应")
            response_obj = next_response

        if _response_was_truncated(response_obj) or _content_looks_truncated(full_content):
            raise OutputLimitExceeded("回答超出总输出上限，未生成完整内容")

    # Defensive invariant: the retry loop should already reject this case.
    if not full_content.strip():
        raise RuntimeError("AI 模型返回空响应")

    # Post-processing
    user_text = " ".join(
        _extract_text_from_content(m.content) for m in lc_messages
        if hasattr(m, "content") and isinstance(m, HumanMessage)
    )
    red_flag = detect_red_flags(user_text)

    summary_json: dict | None = None
    new_status = current_status

    # Parse JSON summary with Pydantic validation
    parsed = _extract_summary_json(full_content)
    min_rounds = 2 if user_requested_summary else 3
    if parsed and round_count >= min_rounds:
        validated = validate_and_clean_summary(parsed)
        if validated:
            summary_json = validated
            new_status = "SUMMARY_READY"
        else:
            logger.warning(f"Summary JSON 校验失败(stream)，原始输出: {str(parsed)[:300]}")
            summary_json = {
                "status": "SUMMARY_READY",
                "chief_complaint": str(parsed.get("chief_complaint", "")),
                "summary_text": str(parsed.get("summary_text", "")),
                "triage_level": parsed.get("triage_level", "observe"),
                "severity": parsed.get("severity", "中度"),
            }
            for key, val in parsed.items():
                if key not in summary_json:
                    summary_json[key] = val
            new_status = "SUMMARY_READY"

    # Status transitions based on agent type
    if red_flag and new_status not in ("SUMMARY_READY", "EVENT_CARD_READY", "CLOSED"):
        new_status = "RISK_ESCALATED"
    elif next_agent == "risk":
        new_status = "RISK_ESCALATED"
    elif new_status == "INIT":
        new_status = "COLLECTING"
    elif round_count >= 2 and new_status == "COLLECTING":
        new_status = "FOLLOW_UP"

    final_state: ConsultationState = {
        "messages": [AIMessage(content=full_content)],
        "session_id": session_id,
        "status": new_status,
        "round_count": round_count + 1,
        "red_flag_detected": red_flag,
        "extracted_fields": existing_extracted_fields or {},
        "summary_json": summary_json,
        "latest_assistant_message": full_content,
        "active_skills": active_skills or [],
        "lang": lang,
        "current_agent": next_agent,
        "user_requested_summary": user_requested_summary,
    }
    yield ("state", final_state)
