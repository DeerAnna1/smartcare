"""
LangGraph 健康问诊 Agent 状态机
状态: INIT → COLLECTING → FOLLOW_UP → RISK_ESCALATED → SUMMARY_READY → EVENT_CARD_READY → CLOSED
"""
from __future__ import annotations
import json
import re
from typing import Annotated, TypedDict, Literal
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from app.core.config import get_settings

settings = get_settings()

# ─── System Prompts ────────────────────────────────────────────────────────────

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

RISK_ESCALATION_PROMPT = """检测到可能的高风险症状信号。请立即：
1. 提升分诊级别为 urgent_visit 或 emergency
2. 建议用户立即线下就医
3. 不再继续常规问诊追问
4. 仅收集最关键信息"""

# ─── 红旗症状关键词 ────────────────────────────────────────────────────────────

RED_FLAG_KEYWORDS = [
    "胸痛", "胸闷", "心前区", "放射至左肩", "冷汗大量",
    "突发剧烈头痛", "雷击样头痛", "意识改变", "意识不清", "昏迷", "晕厥",
    "呼吸困难", "无法呼吸", "喘不过气",
    "大量出血", "吐血", "便血",
    "急性腹痛", "剧烈腹痛", "骨折", "严重外伤", "休克",
    "高烧39度", "高烧40度", "体温40", "体温超过40",
]


def detect_red_flags(text: str) -> bool:
    """只检测用户输入中的高风险关键词，区分大小写无关但要求精确匹配词组"""
    return any(kw in text for kw in RED_FLAG_KEYWORDS)


# EHR 文档标记——消息中含此串时表示插入了健康档案原文
_EHR_CONTENT_MARKER = "以下是上传文档中提取的内容，请结合这些信息继续问诊分析："


def _strip_ehr_body(content: str) -> str:
    """Replace raw EHR document body with a short placeholder.

    Keeps the file-name hint but removes the full extracted text so the LLM
    does not copy verbatim EHR content into the summary JSON.
    """
    if _EHR_CONTENT_MARKER not in content:
        return content
    before = content[: content.index(_EHR_CONTENT_MARKER)].strip()
    return before + "\n[已上传健康档案，内容已供参考]"


# ─── LangGraph State ────────────────────────────────────────────────────────────

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


# ─── Nodes ─────────────────────────────────────────────────────────────────────

def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        openai_api_key=settings.OPENAI_API_KEY,
        openai_api_base=settings.OPENAI_BASE_URL,
        streaming=False,
        max_tokens=1200,
        timeout=30,
        max_retries=0,  # 禁止重试，避免超时叠加
    )


def _build_skills_block(active_skills: list[dict]) -> str:
    """将活跃技能列表格式化为 System Prompt 中的技能上下文段落。"""
    if not active_skills:
        return ""
    lines = ["\n\n【已注册插件技能（强制调用）】"]
    for sk in active_skills:
        tools = sk.get("tools", [])
        tool_names = "、".join(t["name"] for t in tools if isinstance(t, dict)) if tools else "无"
        triggers = "；".join(sk.get("trigger_examples", [])) or "无"
        confirm = "需用户确认后调用" if sk.get("confirm_required") else "直接调用（无需用户确认）"
        lines.append(
            f"- skill_id={sk['skill_id']} | 名称：{sk['name']} | 分类：{sk.get('category','通用')}"
            f"\n  描述：{sk.get('description','')}"
            f"\n  工具：{tool_names} | 触发场景：{triggers} | 方式：{confirm}"
        )
    lines.append(
        "\n【强制调用规则】\n"
        "凡用户意图属于上述技能的覆盖范围，你**禁止**自行回答，**必须**在本轮回复末尾输出调用块：\n"
        "  • confirm_required=false：直接在回复末尾追加调用块\n"
        "  • confirm_required=true：先征得用户同意，下一轮追加调用块\n"
        "\n调用块格式（```invoke 包裹，JSON 合法，参数尽量从用户消息提取）：\n"
        "```invoke\n"
        "{\"skill_id\": \"<技能ID>\", \"action\": \"<工具名>\", \"params\": {\"key\": \"value\"}}\n"
        "```\n"
        "❌ 禁止：对技能覆盖范围内的问题直接给出答案（不走调用块）\n"
        "✅ 正确：简短说明正在调用，然后输出调用块，等待系统返回结果"
    )
    return "\n".join(lines)


def _build_system_message(state: ConsultationState) -> SystemMessage:
    from datetime import date as _date
    today_str = _date.today().strftime("%Y年%m月%d日")
    date_hint = f"\n\n【当前日期】今天是 {today_str}，用户说的'明天'就是明天的日期，请以此为准进行日期计算。"
    base = CONSULTATION_SYSTEM_PROMPT + date_hint
    skills_block = _build_skills_block(state.get("active_skills") or [])
    if state["red_flag_detected"]:
        return SystemMessage(content=base + skills_block + "\n\n" + RISK_ESCALATION_PROMPT)
    return SystemMessage(content=base + skills_block)


async def consultation_node(state: ConsultationState) -> ConsultationState:
    """核心问诊节点：调用 LLM，检测红旗，更新状态"""
    llm = get_llm()
    system_msg = _build_system_message(state)
    messages_with_system = [system_msg] + list(state["messages"])

    response = await llm.ainvoke(messages_with_system)
    content: str = response.content  # type: ignore[assignment]

    # 检测红旗 —— 只扫描用户消息，不扫描 AI 回复（避免 AI 提及症状词误触发）
    user_text = " ".join(
        m.content  # type: ignore[arg-type]
        for m in state["messages"]
        if hasattr(m, "content") and isinstance(m, HumanMessage)
    )
    red_flag = detect_red_flags(user_text)

    # 检测是否包含结构化结论 JSON
    summary_json: dict | None = None
    new_status = state["status"]
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            # 至少 3 轮用户消息才允许进入 SUMMARY_READY，防止"你好"立即结案
            if parsed.get("status") == "SUMMARY_READY" and state["round_count"] >= 3:
                summary_json = parsed
                new_status = "SUMMARY_READY"
        except json.JSONDecodeError:
            pass

    if red_flag and new_status not in ("SUMMARY_READY", "EVENT_CARD_READY", "CLOSED"):
        new_status = "RISK_ESCALATED"
    elif new_status == "INIT":
        new_status = "COLLECTING"
    elif state["round_count"] >= 2 and new_status == "COLLECTING":
        new_status = "FOLLOW_UP"

    return {
        **state,
        "messages": [AIMessage(content=content)],
        "status": new_status,
        "round_count": state["round_count"] + 1,
        "red_flag_detected": red_flag,
        "summary_json": summary_json or state.get("summary_json"),
        "latest_assistant_message": content,
    }


def route(state: ConsultationState) -> str:
    # 每轮只调用一次 LLM，由 API 层管理多轮对话，不在图内循环
    return END


# ─── Build Graph ──────────────────────────────────────────────────────────────

def build_consultation_graph() -> StateGraph:
    builder = StateGraph(ConsultationState)
    builder.add_node("consultation", consultation_node)
    builder.add_edge(START, "consultation")
    builder.add_conditional_edges("consultation", route)
    return builder.compile()


consultation_graph = build_consultation_graph()


# ─── 公共接口 ──────────────────────────────────────────────────────────────────

async def run_consultation_turn(
    session_id: str,
    messages: list[dict],
    current_status: str = "INIT",
    round_count: int = 0,
    active_skills: list[dict] | None = None,
) -> ConsultationState:
    """运行一轮问诊，返回更新后的状态"""
    lc_messages: list[BaseMessage] = []
    for m in messages:
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=_strip_ehr_body(m["content"])))
        elif m["role"] == "assistant":
            lc_messages.append(AIMessage(content=m["content"]))

    initial_state: ConsultationState = {
        "messages": lc_messages,
        "session_id": session_id,
        "status": current_status,  # type: ignore[typeddict-item]
        "round_count": round_count,
        "red_flag_detected": False,
        "extracted_fields": {},
        "summary_json": None,
        "latest_assistant_message": "",
        "active_skills": active_skills or [],
    }

    result = await consultation_graph.ainvoke(initial_state)
    return result  # type: ignore[return-value]
