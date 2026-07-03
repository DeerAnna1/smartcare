"""健康问诊工作区 API"""
import asyncio
import json
import logging
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.concurrency import get_request_semaphore
from sqlalchemy import select, delete, update, or_
from sqlalchemy.exc import IntegrityError
from app.api.deps.auth import get_current_user_required
from app.core.database import get_db, AsyncSessionLocal
from app.core.rate_limit import limiter
from app.models.models import (
    ConsultationSession,
    ConversationMessage,
    AuditLog,
    HandoffTicket,
    HealthEvent,
    LabReport,
    MemoryFact,
    SkillPackage,
    ToolInvocationLog,
    User,
    UserOAuthCredential,
    VitalStreamEvent,
)
from app.services.feishu_notifier import (
    get_patient_display_name,
    resolve_feishu_config,
    send_feishu_alert,
)
from app.schemas.schemas import (
    CreateSessionRequest, SessionResponse,
    SendMessageRequest, SessionMessageResponse,
    SessionSummaryResponse,
    SessionDetailResponse, MessageItem,
    CreateEventCardRequest, EventCardResponse,
)
from app.orchestrators.consultation import run_consultation_turn, run_consultation_turn_stream, detect_red_flags, cleanup_checkpoint, OutputLimitExceeded
from app.services.registration import RegistrationService
from app.services.drug_interaction import query_drug_interactions, ZH_TO_EN
from app.services.risk_guardrail import emergency_reply, evaluate_risk, evaluate_risk_with_llm
from app.services.tool_registry import execute_tool_call
from app.core.observability import flush_langfuse


_background_generation_tasks: set[asyncio.Task] = set()


async def _stream_text_events(content: str, chunk_size: int = 32):
    """Yield assistant text as SSE token events instead of one large done payload."""
    if not content:
        return
    for start in range(0, len(content), chunk_size):
        chunk = content[start:start + chunk_size]
        yield f"event: token\ndata: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        # Yield control without imposing an artificial delay so ASGI can flush
        # each real SSE event as soon as it is available.
        await asyncio.sleep(0)


def _queue_feishu_alert(
    user: User,
    *,
    reason: str,
    evidence: list[str],
    session_id: str,
) -> None:
    """后台发送飞书告警，不阻塞高风险接管响应。"""
    config = resolve_feishu_config(user)
    if not config.enabled or not config.webhook_url:
        return
    asyncio.create_task(
        send_feishu_alert(
            webhook_url=config.webhook_url,
            webhook_secret=config.webhook_secret,
            patient_name=get_patient_display_name(user),
            risk_level="high",
            reason=reason,
            evidence=evidence,
            session_id=session_id,
        )
    )


def _get_user_llm_config(user: User) -> dict | None:
    """从用户 preferences 中读取自定义 LLM 配置，未配置返回 None。"""
    try:
        prefs = json.loads(user.preferences or "{}")
    except json.JSONDecodeError:
        return None
    cfg = prefs.get("llm_config")
    if cfg and cfg.get("api_key"):
        return cfg
    return None

router = APIRouter(prefix="/consultations", tags=["健康问诊"])


async def _require_request_slot():
    """FastAPI dependency: acquire request concurrency semaphore for the request lifetime."""
    sem = get_request_semaphore()
    await asyncio.wait_for(sem.acquire(), timeout=60)
    try:
        yield
    finally:
        sem.release()


# 常见商品名/中成药名补充。未必能映射到 openFDA 通用名，但至少应被识别出来，
# 以便查询服务如实返回“未能确认”，而不是直接提示未识别到药名。
PRODUCT_NAME_ALIASES: dict[str, str] = {
    "999感冒灵": "999感冒灵",
    "三九感冒灵": "999感冒灵",
    "感冒灵颗粒": "感冒灵颗粒",
    "健胃消食片": "健胃消食片",
    "连花清瘟": "连花清瘟",
    "连花清瘟胶囊": "连花清瘟",
    "板蓝根": "板蓝根",
    "板蓝根颗粒": "板蓝根",
    "复方甘草片": "复方甘草片",
    "甘草片": "复方甘草片",
    "藿香正气水": "藿香正气水",
    "藿香正气液": "藿香正气水",
    "六味地黄丸": "六味地黄丸",
    "牛黄解毒片": "牛黄解毒片",
    "云南白药": "云南白药",
    "双黄连": "双黄连",
    "双黄连口服液": "双黄连",
    "蒲地蓝": "蒲地蓝",
    "蒲地蓝消炎口服液": "蒲地蓝",
    "开瑞坦": "氯雷他定",
    "氯雷他定": "氯雷他定",
    "西替利嗪": "西替利嗪",
    "达喜": "铝碳酸镁",
    "铝碳酸镁": "铝碳酸镁",
    "吗丁啉": "多潘立酮",
    "芬必得": "布洛芬",
    "泰诺": "对乙酰氨基酚",
    "感康": "感康",
    "白加黑": "白加黑",
    "新康泰克": "新康泰克",
}


def _build_iot_emergency_message(vital: VitalStreamEvent) -> str:
    return (
        "检测到穿戴设备高风险生命体征，我已自动触发人工接管。"
        f"当前数据：{vital.metric}={vital.value}{vital.unit}。"
        "请立即停止剧烈活动，并尽快就医或联系急救。"
    )


def _extract_drug_names_from_text(text: str) -> list[str]:
    """从用户自由文本中抽取药名（中英文），保持出现顺序去重。"""
    s = (text or "").strip()
    if not s:
        return []

    found: list[str] = []

    # 1) 中文药名匹配（按长度降序，避免短词抢占）
    zh_names = sorted(ZH_TO_EN.keys(), key=len, reverse=True)
    for zh in zh_names:
        if zh in s and zh not in found:
            found.append(zh)

    # 1.1) 常见商品名/中成药名匹配
    product_names = sorted(PRODUCT_NAME_ALIASES.keys(), key=len, reverse=True)
    for product_name in product_names:
        canonical_name = PRODUCT_NAME_ALIASES[product_name]
        if product_name in s and canonical_name not in found:
            found.append(canonical_name)

    # 2) 英文药名匹配（按单词匹配）
    en_set = {v.lower() for v in ZH_TO_EN.values()}
    for token in re.findall(r"[A-Za-z][A-Za-z\-]{1,}", s):
        t = token.lower()
        if t in en_set and t not in [x.lower() for x in found]:
            found.append(t)

    # 3) 兜底：若命中“X和Y可以吗/能一起吃吗”这类句式，允许把商品名短语抽出来。
    if len(found) < 2:
        pair_match = re.search(
            r"(?:吃|用)?\s*([^，。；,]+?)\s*(?:和|与|跟|及)\s*([^，。；,]+?)(?:能|可以|可否|有|会|吗|一起|同时|同服|同用)",
            s,
        )
        if pair_match:
            for group in pair_match.groups():
                candidate = group.strip(" 这两种药物药片颗粒胶囊一起同时服用吃可以吗有问题呢")
                if candidate and candidate not in found:
                    found.append(candidate)
                if len(found) >= 2:
                    break

    return found


def _should_force_registration_skill(user_text: str, active_skills: list[dict]) -> tuple[bool, dict]:
    """
    当用户明显在问'挂号/预约/查号源/排班'时，兜底强制触发挂号预约技能。
    目的：避免 LLM 漏输出 invoke 块或 native function calling 不可用时技能未调用。
    """
    if not any(s.get("skill_id") == "appointment-booking" for s in active_skills):
        return False, {}

    text = (user_text or "").strip()
    intent_patterns = [
        r"挂号", r"预约", r"查号源", r"排班", r"看.+科", r"挂.+科",
        r"有没有号", r"有号吗", r"号源", r"就诊", r"门诊",
        r"帮我挂", r"帮我约", r"能挂", r"能约", r"想看",
        r"book.*appointment", r"schedule.*doctor", r"make.*appointment",
    ]
    has_intent = any(re.search(p, text) for p in intent_patterns)
    if not has_intent:
        return False, {}

    # Extract department (longer names first to avoid partial matches)
    dept_match = re.search(r"(心内科|骨科|皮肤科|妇产科|儿科|神经内科|消化内科|呼吸内科|眼科|耳鼻喉科|口腔科|泌尿外科|内分泌科|中医科|急诊科|内科|外科|妇科|产科|男科|肿瘤科|精神科|心理科|康复科|风湿免疫科|血液科|肾内科|肝胆外科|普外科|胸外科|血管外科|疼痛科|营养科|全科|感染科|变态反应科|心内|消化|呼吸|神经)", text)
    dept = dept_match.group(1) if dept_match else "内科"

    # Extract hospital
    hospital = ""
    hosp_match = re.search(r"([一-鿿]{2,}(?:医院|诊所|卫生院|中心))", text)
    if hosp_match:
        hospital = hosp_match.group(1)

    # Extract date hint
    date_hint = "明天"
    for word in ["今天", "明天", "后天", "大后天"]:
        if word in text:
            date_hint = word
            break
    date_match = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", text)
    if date_match:
        date_hint = date_match.group(1)

    return True, {"department": dept, "hospital": hospital, "date": date_hint}


def _should_force_drug_skill(user_text: str, active_skills: list[dict]) -> tuple[bool, list[str]]:
    """
    当用户明显在问'两药能否同用/相互作用'时，兜底强制触发药物相互作用技能。
    目的：避免 LLM 漏输出 invoke 块导致技能未调用。
    不依赖 active_skills 中是否注册了 drug-safety，直接可用。
    """
    text = (user_text or "").lower()
    intent_patterns = [
        r"相互作用", r"能一起", r"可以一起", r"一起用", r"同时用", r"同用",
        r"合用", r"冲突", r"配伍", r"能不能", r"可以吗",
        r"一起吃", r"同时在吃", r"同时吃", r"同吃", r"同服", r"并用", r"联用",
        r"有没有问题", r"有问题吗", r"是否安全", r"安全吗",
        r"间隔.*吃", r"先后.*吃", r"影响.*效果", r"降低.*疗效",
        r"可以.*同时", r"能.*同时", r"一起.*服用", r"同时.*服用",
    ]
    has_intent = any(re.search(p, text) for p in intent_patterns)
    drugs = _extract_drug_names_from_text(user_text)
    if has_intent and len(drugs) >= 2:
        return True, drugs[:4]
    return False, drugs


def _should_force_literature_skill(user_text: str, active_skills: list[dict]) -> tuple[bool, dict]:
    """明确的医学文献检索请求直接走 PubMed，不先等待模型决定是否调用工具。"""
    skill = next((s for s in active_skills if s.get("skill_id") == "medical-literature-review"), None)
    if not skill:
        return False, {}
    text = (user_text or "").strip()
    lowered = text.casefold()
    if not any(token in lowered for token in ("文献", "研究", "pmid", "pubmed", "论文")):
        return False, {}

    count_match = re.search(r"(?:返回|列出|找|检索|搜索)?\s*(\d{1,2})\s*篇", text)
    count = max(1, min(int(count_match.group(1)) if count_match else 3, 10))
    # 这里只抽取用户主题；英文 PubMed 检索式由运行时动态生成，禁止主题白名单和静态结果。
    topic_matches = list(re.finditer(r"(?:搜索|检索|查找|查询)\s*([^，,]+)", text))
    topic = topic_matches[-1].group(1) if topic_matches else text
    topic = re.sub(r"^(?:请|帮我|请帮我)?\s*(?:搜索|检索|查找|查询)", "", topic)
    topic = re.sub(r"(?:，|,)?\s*(?:返回|列出|给出|找出)\s*\d{1,2}\s*篇.*$", "", topic)
    topic = re.sub(r"(?:，|,)?\s*并?标注\s*(?:PMID|pmid).*$", "", topic)
    topic = re.sub(r"(?:相关)?(?:的)?(?:医学)?(?:研究|文献|论文)\s*$", "", topic)
    topic = re.sub(r"^(?:please\s+)?(?:search|find|retrieve|look up)\s+", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"(?:,\s*)?(?:return|list|show|find)\s+\d{1,2}\s+(?:papers|articles|studies).*$", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\s+(?:medical\s+)?(?:research|literature|papers|studies)\s*$", "", topic, flags=re.IGNORECASE)
    topic = topic.strip(" ，,。")
    if not topic:
        return False, {}
    return True, {"topic": topic, "maxResults": count, "summaryCount": count}


def _should_force_drug_profile(user_text: str, active_skills: list[dict]) -> tuple[bool, dict]:
    """识别明确要求通过 OpenFDA MCP 查询药品档案的请求。"""
    text = (user_text or "").strip()
    lowered = text.casefold()
    if "openfda" not in lowered or not any(word in lowered for word in ("药品档案", "适应症", "警告", "drug profile")):
        return False, {}
    has_profile_tool = any(
        t.get("name", "").endswith("__openfda_drug_profile")
        for skill in active_skills for t in skill.get("tools", []) if isinstance(t, dict)
    )
    if not has_profile_tool:
        return False, {}
    known = _extract_drug_names_from_text(text)
    if known:
        drug = ZH_TO_EN.get(known[0], known[0])
    else:
        candidates = re.findall(r"\b[a-z][a-z0-9-]{2,}\b", lowered)
        ignored = {"openfda", "mcp", "drug", "profile", "fda"}
        drug = next((word for word in candidates if word not in ignored), "")
    return (bool(drug), {"drug": drug} if drug else {})


# ─── 自然语言日期解析（简单版）────────────────────────────────────────────────────

def _parse_date_hint(hint: str) -> str:
    """将"明天"/"后天"/"今天"等自然语言转为 YYYY-MM-DD，无法解析则原样返回。"""
    today = date.today()
    mapping = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}
    for word, delta in mapping.items():
        if word in hint:
            return (today + timedelta(days=delta)).strftime("%Y-%m-%d")
    return hint  # 已是 YYYY-MM-DD 或未知，原样传入


# ─── 技能执行引擎 ─────────────────────────────────────────────────────────────────

async def _execute_skill(
    skill_id: str, action: str, params: dict,
    active_skills: list[dict], db: AsyncSession, user_id: str,
    event_callback=None,
) -> dict:
    """统一技能执行入口，只返回真实工具或真实业务服务的结果。"""

    # ── 挂号预约：走真实 RegistrationService ──────────────────────────────────────
    if skill_id == "appointment-booking":
        svc = RegistrationService(db)
        hospital_kw = params.get("hospital") or ""
        dept_kw = (params.get("department") or params.get("dept") or
                   next((s.get("recommended_department", "") for s in active_skills
                         if s["skill_id"] == skill_id), "") or "内科")
        raw_date = params.get("date") or "明天"
        query_date = _parse_date_hint(raw_date)

        if action in ("query_schedule", "search_doctor_schedule", ""):
            result = await svc.search_by_department_name(
                hospital_name=hospital_kw,
                department_name=dept_kw,
                date=query_date,
            )
            if "error" in result:
                return {"success": False, "message": result["error"], "data": {}}
            slots = result.get("slots", [])
            return {
                "success": True,
                "message": f"已查询 {result['hospital']['name']} {result['department']['name']} {query_date} 排班",
                "data": {
                    "hospital": result["hospital"]["name"],
                    "department": result["department"]["name"],
                    "date": query_date,
                    "slots": [
                        {
                            "time": s["time_slot"],
                            "doctor": s["doctor_name"],
                            "title": s["doctor_title"],
                            "bio": s["doctor_bio"],
                            "fee": s["fee"],
                            "remaining": s["remaining_quota"],
                            "available": s["available"],
                        }
                        for s in slots
                    ],
                },
            }

        if action == "lock_slot":
            schedule_id = params.get("schedule_id", "")
            if not schedule_id:
                return {"success": False, "message": "缺少 schedule_id 参数", "data": {}}
            result = await svc.lock_slot(
                user_id=user_id,
                schedule_id=schedule_id,
                patient_name=params.get("patient_name", "患者"),
                patient_id_last4=params.get("patient_id_last4", "0000"),
            )
            return result if result.get("success") else {
                "success": False, "message": result.get("error", "锁号失败"), "data": {}
            }

        return {"success": False, "message": f"未知 action: {action}", "data": {}}

    # ── 药物相互作用：优先走 MCP openfda-drug-safety，回退到内置 API ────────────
    if skill_id == "drug-safety":
        if action == "drug_profile":
            profile_tool = next(
                (
                    t for skill in active_skills for t in skill.get("tools", [])
                    if isinstance(t, dict) and t.get("provider")
                    and t.get("name", "").endswith("__openfda_drug_profile")
                ),
                None,
            )
            if not profile_tool:
                return {"success": False, "message": "未绑定 OpenFDA MCP 药品档案工具", "data": {}}
            drug = str(params.get("drug", "")).strip()
            properties = profile_tool.get("parameters", {}).get("properties", {})
            arg_name = next(
                (name for name in ("drug", "drug_name", "generic_name", "name", "search") if name in properties),
                "drug",
            )
            tool_args = {arg_name: drug}
            from app.mcp.manager import mcp_manager
            try:
                mcp_result = await asyncio.wait_for(
                    mcp_manager.invoke(profile_tool["provider"], profile_tool["name"], tool_args), timeout=25
                )
            except asyncio.TimeoutError:
                failed = {"status": "failed", "error": "OpenFDA MCP 调用超时"}
                return {
                    "success": False, "message": failed["error"], "data": {},
                    "tool_runs": [{"name": profile_tool["name"], "args": tool_args, "result": failed}],
                }
            tool_runs = [{"name": profile_tool["name"], "args": tool_args, "result": mcp_result}]
            if mcp_result.get("status") != "success":
                return {
                    "success": False, "message": mcp_result.get("error") or "OpenFDA MCP 调用失败",
                    "data": {}, "tool_runs": tool_runs,
                }
            mcp_data = mcp_result.get("result", {})
            content = mcp_data.get("content", []) if isinstance(mcp_data, dict) else []
            if not any(isinstance(block, dict) and block.get("text") for block in content):
                return {
                    "success": False, "message": "OpenFDA MCP 未返回有效药品档案",
                    "data": {}, "tool_runs": tool_runs,
                }
            return {
                "success": True,
                "message": "OpenFDA MCP 药品档案查询完成",
                "data": mcp_data,
                "tool_runs": tool_runs,
            }

        drugs = params.get("drugs") or params.get("drug_list") or []
        d1 = params.get("drug1") or ""
        d2 = params.get("drug2") or ""
        if not drugs:
            drugs = [x for x in [d1, d2] if x]
        if isinstance(drugs, str):
            drugs = [d.strip() for d in drugs.replace("、", ",").split(",")]
        drugs = [d for d in drugs if isinstance(d, str) and d.strip()]
        if len(drugs) < 2:
            return {
                "success": False,
                "message": "未能识别到两种有效药物名称，请提供更明确的药品通用名（如阿司匹林、布洛芬）。",
                "data": {"drugs": drugs},
            }
        # 优先使用 MCP openfda-drug-safety 工具
        mcp_tool = next(
            (
                t
                for skill in active_skills
                for t in skill.get("tools", [])
                if isinstance(t, dict)
                and t.get("provider")
                and t.get("name", "").startswith("openfda-drug-safety__")
                and "drugs" in (t.get("parameters", {}).get("properties", {}))
            ),
            None,
        )
        if mcp_tool:
            from app.mcp.manager import mcp_manager
            mcp_args = {"drugs": drugs}
            mcp_result = await mcp_manager.invoke(mcp_tool["provider"], mcp_tool["name"], mcp_args)
            if mcp_result.get("status") == "success":
                return {
                    "success": True,
                    "message": "药物安全数据查询完成",
                    "data": mcp_result.get("result", {}),
                }
            return {
                "success": False,
                "message": mcp_result.get("error") or "药物安全数据服务调用失败",
                "data": mcp_result.get("result", {}),
            }
        return await query_drug_interactions(drugs)

    if skill_id == "medical-literature-review":
        skill = next((s for s in active_skills if s.get("skill_id") == skill_id), None)
        search_tool = next(
            (t for t in (skill or {}).get("tools", []) if t.get("name", "").endswith("__pubmed_search_articles")),
            None,
        )
        fetch_tool = next(
            (t for t in (skill or {}).get("tools", []) if t.get("name", "").endswith("__pubmed_fetch_articles")),
            None,
        )
        if not search_tool or not search_tool.get("provider") or not fetch_tool or not fetch_tool.get("provider"):
            return {"success": False, "message": "医学文献检索技能未绑定 PubMed MCP 搜索工具", "data": {}}

        try:
            from app.mcp.manager import mcp_manager
            from app.services.pubmed_query import build_pubmed_query

            limit = int(params.get("maxResults", 3))
            query = await build_pubmed_query(str(params.get("topic") or params.get("query") or ""))
            search_args = {"query": query, "maxResults": limit, "sort": "relevance"}
            search_call_id = str(uuid.uuid4())
            if event_callback:
                await event_callback("tool_start", {
                    "call_id": search_call_id, "name": search_tool["name"], "args": search_args,
                })
            try:
                search_result = await asyncio.wait_for(
                    mcp_manager.invoke(search_tool["provider"], search_tool["name"], search_args), timeout=25
                )
            except Exception as exc:
                search_result = {"status": "failed", "error": str(exc).strip() or exc.__class__.__name__}
            if event_callback:
                await event_callback("tool_end", {
                    "call_id": search_call_id, "name": search_tool["name"], "result": search_result,
                })
            tool_runs = [{
                "call_id": search_call_id, "name": search_tool["name"],
                "args": search_args, "result": search_result,
            }]
            if search_result.get("status") != "success":
                return {"success": False, "message": search_result.get("error") or "PubMed MCP 搜索失败", "data": {}, "tool_runs": tool_runs}

            search_data = search_result.get("result", {})
            structured = search_data.get("structuredContent", {}) if isinstance(search_data, dict) else {}
            pmids = [str(pmid) for pmid in structured.get("pmids", [])]
            if not pmids:
                text_content = "\n".join(
                    str(block.get("text", "")) for block in search_data.get("content", []) if isinstance(block, dict)
                )
                match = re.search(r"\*\*PMIDs:\*\*\s*([0-9,\s]+)", text_content)
                pmids = re.findall(r"\d+", match.group(1)) if match else []
            pmids = pmids[:limit]
            if len(pmids) < limit or len(set(pmids)) < limit or not all(p.isdigit() for p in pmids):
                return {"success": False, "message": f"PubMed MCP 未返回 {limit} 条唯一有效 PMID", "data": {}, "tool_runs": tool_runs}

            fetch_args = {"pmids": pmids, "includeMesh": True}
            fetch_call_id = str(uuid.uuid4())
            if event_callback:
                await event_callback("tool_start", {
                    "call_id": fetch_call_id, "name": fetch_tool["name"], "args": fetch_args,
                })
            try:
                fetch_result = await asyncio.wait_for(
                    mcp_manager.invoke(fetch_tool["provider"], fetch_tool["name"], fetch_args), timeout=25
                )
            except Exception as exc:
                fetch_result = {"status": "failed", "error": str(exc).strip() or exc.__class__.__name__}
            if event_callback:
                await event_callback("tool_end", {
                    "call_id": fetch_call_id, "name": fetch_tool["name"], "result": fetch_result,
                })
            tool_runs.append({
                "call_id": fetch_call_id, "name": fetch_tool["name"],
                "args": fetch_args, "result": fetch_result,
            })
            if fetch_result.get("status") != "success":
                return {"success": False, "message": fetch_result.get("error") or "PubMed MCP 文献详情获取失败", "data": {}, "tool_runs": tool_runs}
            fetch_data = fetch_result.get("result", {})
            fetch_structured = fetch_data.get("structuredContent", {}) if isinstance(fetch_data, dict) else {}
            summaries = fetch_structured.get("summaries") or fetch_structured.get("articles") or []
            if len(summaries) < limit:
                return {"success": False, "message": f"PubMed MCP 只返回了 {len(summaries)} 篇有效文献详情", "data": {}, "tool_runs": tool_runs}

            # 逐篇解释严格来自 fetch 返回的 PubMed 摘要；翻译失败时保留英文摘录。
            from app.services.pubmed_query import extract_abstract_explanation, translate_en_to_zh
            for index, article in enumerate(summaries[:limit], 1):
                abstract = str(article.get("abstractText") or article.get("abstract") or "")
                excerpt = extract_abstract_explanation(abstract)
                if not excerpt:
                    article["explanation"] = ""
                    article["explanationLanguage"] = "missing"
                else:
                    try:
                        translated = await translate_en_to_zh(excerpt)
                    except Exception:
                        translated = ""
                    article["explanation"] = translated or excerpt
                    article["explanationLanguage"] = "zh" if translated else "en"
                if event_callback:
                    await event_callback("content_delta", {"index": index, "article": article})

            return {
                "success": True,
                "message": "PubMed MCP 文献检索完成",
                "data": fetch_data,
                "tool_runs": tool_runs,
            }
        except asyncio.TimeoutError:
            return {"success": False, "message": "PubMed MCP 调用超时", "data": {}}
        except Exception as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            return {"success": False, "message": f"PubMed MCP 调用或结果复核失败：{detail}", "data": {}}

    # ── 健康任务同步：未接入真实平台 ─────────────────────────────────────────────────
    if skill_id == "task-sync":
        return {
            "success": False,
            "message": "任务同步功能暂未接入真实平台（飞书/Notion），请等待后续版本",
            "data": {"status": "not_configured"},
        }

    # ── 跨 App 智能体：未接入真实能力 ───────────────────────────────────────────────
    if skill_id == "cross-app-agent":
        return {
            "success": False,
            "message": "跨应用操作功能暂未接入受控能力（AutoGLM），请等待后续版本",
            "data": {"status": "not_configured"},
        }

    return {"success": False, "message": f"技能 {skill_id} 暂未实现", "data": {}}


def _format_pubmed_article(article: dict, index: int) -> list[str]:
    lines = [f"{index}. **{article.get('title', '未提供标题')}**"]
    pmid = article.get("pmid") or article.get("uid") or article.get("id") or "未提供"
    lines.append(f"   PMID：{pmid}")
    authors = article.get("authors")
    if isinstance(authors, list):
        author_names = []
        for author in authors:
            if not isinstance(author, dict):
                name = str(author).strip()
            else:
                name = str(
                    author.get("name") or author.get("fullName")
                    or author.get("collectiveName") or ""
                ).strip()
                if not name:
                    name = " ".join(
                        str(author.get(key, "")).strip()
                        for key in ("foreName", "lastName") if author.get(key)
                    )
            if name:
                author_names.append(name)
        authors = ", ".join(author_names)
    if authors:
        lines.append(f"   作者：{authors}")
    source_parts = [
        str(x) for x in (
            article.get("source") or article.get("journal"),
            article.get("pubDate") or article.get("published"),
        ) if x
    ]
    if source_parts:
        lines.append(f"   来源：{'，'.join(source_parts)}")
    pubmed_url = article.get("pubmedUrl") or article.get("url")
    if pubmed_url:
        lines.append(f"   PubMed：{pubmed_url}")
    explanation = str(article.get("explanation") or "").strip()
    explanation_language = article.get("explanationLanguage")
    if explanation:
        label = "摘要内容整理" if explanation_language == "zh" else "PubMed 摘要摘录（英文）"
        lines.append(f"   {label}：{explanation}")
    else:
        lines.append("   摘要内容整理：PubMed 未提供可用摘要，无法进一步概述。")
    return lines


def _format_skill_result(skill_id: str, action: str, result: dict, active_skills: list[dict]) -> str:
    """将技能调用结果格式化为对话中可展示的文本块。"""
    skill_name = next((s["name"] for s in active_skills if s["skill_id"] == skill_id), skill_id)
    if not result.get("success"):
        return f"\n\n---\n**⚠️ 【{skill_name}】调用失败**：{result.get('message', '未知错误')}\n---"

    data = result.get("data", {})
    msg = result.get("message", "")
    lines = [f"\n\n---\n**✅ 【{skill_name}】{msg}**"]

    if skill_id == "appointment-booking":
        slots = data.get("slots", [])
        hospital = data.get("hospital", "")
        dept = data.get("department", "")
        query_date = data.get("date", "")
        if hospital:
            lines.append(f"医院：{hospital}  科室：{dept}  日期：{query_date}")
        available = [s for s in slots if s.get("available")]
        unavailable = [s for s in slots if not s.get("available")]
        if available:
            lines.append("可预约时段：")
            for s in available:
                remaining = f"  余 {s['remaining']} 号" if s.get("remaining") is not None else ""
                fee = f"  ¥{s['fee']}" if s.get("fee") else ""
                lines.append(f"- {s['time']}  {s['doctor']} ({s.get('title','')}){remaining}{fee}")
        if unavailable:
            lines.append("已满号：")
            for s in unavailable:
                lines.append(f"- ~~{s['time']}  {s['doctor']}~~ （号源已满）")
        if not slots:
            lines.append("暂无可用号源，建议更换日期或科室。")

    elif skill_id == "drug-safety" and action == "drug_profile":
        content_blocks = data.get("content", []) if isinstance(data, dict) else []
        text_blocks = [
            str(block.get("text", "")) for block in content_blocks
            if isinstance(block, dict) and block.get("text")
        ]
        lines.extend(text_blocks)
        lines.append("数据来源：美国 FDA OpenFDA 数据库")

    elif skill_id == "drug-safety":
        en_names = data.get("en_names", [])
        level = data.get("interaction_level", "")
        pairs = data.get("pairs", [])
        lines.append(f"相互作用风险级别：**{level}**")
        if en_names:
            lines.append(f"英文对应：{' + '.join(en_names)}")
        desc = data.get("description", "")
        if desc:
            for line in desc.split("\n"):
                if line.strip():
                    lines.append(line.strip())
        lines.append(f"建议：{data.get('recommendation', '')}")
        if data.get("source"):
            lines.append(f"数据来源：{data['source']}")

    elif skill_id == "medical-literature-review":
        structured = data.get("structuredContent", {}) if isinstance(data, dict) else {}
        summaries = (structured.get("summaries") or structured.get("articles") or []) if isinstance(structured, dict) else []
        if summaries:
            for index, article in enumerate(summaries, 1):
                lines.extend(_format_pubmed_article(article, index))
        else:
            content_blocks = data.get("content", []) if isinstance(data, dict) else []
            text_blocks = [block.get("text", "") for block in content_blocks if isinstance(block, dict) and block.get("type") == "text"]
            if text_blocks:
                lines.append("\n".join(text_blocks))
            else:
                lines.append("PubMed 未返回可展示的文献记录。")
        lines.append("数据来源：PubMed（美国国家医学图书馆）")

    elif skill_id == "task-sync":
        lines.append(f"已在 {data.get('platform','')} 创建任务：**{data.get('task_title','')}**（ID: {data.get('task_id','')}）")

    elif skill_id == "cross-app-agent":
        lines.append(f"已在【{data.get('app','')}】完成操作，共执行 {data.get('steps_completed',0)} 步。")

    lines.append("---")
    return "\n".join(lines)


async def _record_tool_invocation(
    skill_id: str,
    params: dict,
    result: dict,
    latency_ms: int,
    active_skills: list[dict],
    db: AsyncSession,
    tool_name: str | None = None,
) -> None:
    """记录技能调用日志；失败不影响主流程。"""
    try:
        pkg_result = await db.execute(
            select(SkillPackage).where(SkillPackage.skill_id == skill_id)
        )
        pkg = pkg_result.scalar_one_or_none()
        log = ToolInvocationLog(
            id=str(uuid.uuid4()),
            skill_id=pkg.id if pkg else None,
            trace_id=str(uuid.uuid4()),
            tool_name=tool_name or next((s["name"] for s in active_skills if s["skill_id"] == skill_id), skill_id),
            request_json=json.dumps(params, ensure_ascii=False),
            response_json=json.dumps(result.get("data", {}), ensure_ascii=False),
            latency_ms=latency_ms,
            result_status="success" if result.get("success") else "failed",
            error_reason="" if result.get("success") else result.get("message", ""),
        )
        db.add(log)
    except Exception:
        pass


async def _record_workflow_runs(
    skill_id: str, tool_runs: list[dict], active_skills: list[dict], db: AsyncSession
) -> None:
    """Persist each real MCP call under its actual tool name."""
    for run in tool_runs:
        raw_result = run.get("result", {})
        normalized = {
            "success": raw_result.get("status") == "success",
            "message": raw_result.get("error", ""),
            "data": raw_result.get("result", {}),
        }
        await _record_tool_invocation(
            skill_id, run.get("args", {}), normalized, 0, active_skills, db,
            tool_name=run.get("name"),
        )


async def _process_skill_invocations(
    content: str, active_skills: list[dict], db: AsyncSession, user_id: str
) -> str:
    """检测并处理回复中的 ```invoke 块，替换为技能执行结果（兼容未闭合的块）。"""
    pattern = re.compile(r"```invoke\s*(\{.*?\})\s*(?:```|$)", re.DOTALL)
    matches = list(pattern.finditer(content))
    if not matches:
        return content

    result_str = content
    for m in reversed(matches):  # 从后往前替换，保持偏移
        try:
            invoke_data = json.loads(m.group(1))
            skill_id = invoke_data.get("skill_id", "")
            action = invoke_data.get("action", "")
            params = invoke_data.get("params", {})
            t_start = time.time()
            result = await _execute_skill(skill_id, action, params, active_skills, db, user_id)
            latency_ms = int((time.time() - t_start) * 1000)
            formatted = _format_skill_result(skill_id, action, result, active_skills)
            result_str = result_str[: m.start()] + formatted + result_str[m.end():]
            await _record_tool_invocation(skill_id, params, result, latency_ms, active_skills, db)
        except Exception:
            # 解析或执行失败时保留原块，避免把真实错误伪装成成功内容。
            pass

    return result_str


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """返回当前用户的历史问诊列表（仅包含有过至少一轮交互的会话）"""
    result = await db.execute(
        select(ConsultationSession)
        .where(ConsultationSession.user_id == user.id)
        .order_by(ConsultationSession.updated_at.desc())
    )
    sessions = result.scalars().all()
    items = []
    _skill_tag_re = re.compile(r"[✅⚠️]\s*【([^】]+)】")
    for s in sessions:
        # Skip sessions with no user messages
        try:
            msgs = json.loads(s.raw_messages or "[]")
            user_msg_count = sum(1 for m in msgs if isinstance(m, dict) and m.get("role") == "user")
            if user_msg_count == 0:
                continue
        except Exception:
            continue
        extracted = json.loads(s.extracted_fields or "{}")
        # 从消息中提取技能调用标签
        skill_tags: list[str] = []
        try:
            msgs = json.loads(s.raw_messages or "[]")
            seen: set[str] = set()
            for m in msgs:
                if isinstance(m, dict) and m.get("role") == "tool" and m.get("skill_name"):
                    skill_name = str(m["skill_name"])
                    if skill_name not in seen:
                        seen.add(skill_name)
                        skill_tags.append(skill_name)
                if isinstance(m, dict) and m.get("role") == "assistant":
                    for match in _skill_tag_re.findall(m.get("content", "")):
                        if match not in seen:
                            seen.add(match)
                            skill_tags.append(match)
        except Exception:
            pass

        # 获取显示标题：优先使用 chief_complaint，然后是 summary，最后从消息中提取
        display_title = extracted.get("chief_complaint") or s.summary or ""
        if not display_title:
            # 从第一条用户消息中提取摘要（截取前50个字符）
            try:
                msgs = json.loads(s.raw_messages or "[]")
                for m in msgs:
                    if isinstance(m, dict) and m.get("role") == "user":
                        content = m.get("content", "")
                        # 处理多模态消息（content 为列表）
                        if isinstance(content, list):
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    content = part.get("text", "")
                                    break
                        if isinstance(content, str) and content.strip():
                            # 去除文件上传标记
                            clean_content = content.split("[已上传文件:")[0].split("[已上传图片:")[0].strip()
                            if clean_content:
                                display_title = clean_content[:50] + ("..." if len(clean_content) > 50 else "")
                            break
            except Exception:
                pass

        # 如果仍然没有标题，使用默认值
        if not display_title:
            display_title = "健康咨询"

        latest_row = await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == s.id, ConversationMessage.role == "assistant")
            .order_by(ConversationMessage.created_at.desc())
            .limit(1)
        )
        latest_message = latest_row.scalar_one_or_none()

        items.append(SessionResponse(
            session_id=s.id,
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
            chief_complaint=display_title,
            triage_level=s.triage_level or "",
            skill_tags=skill_tags,
            latest_message_id=latest_message.id if latest_message else None,
            generation_status=latest_message.status if latest_message else None,
        ))
    return items


@router.post("", response_model=SessionResponse)
async def create_session(
    body: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    session = ConsultationSession(user_id=user.id)
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return SessionResponse(
        session_id=session.id,
        status=session.status,
        created_at=session.created_at,
    )


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(ConsultationSession).where(
            ConsultationSession.id == session_id,
            ConsultationSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    raw: list[dict] = json.loads(session.raw_messages or "[]")
    # 判断是否检测过红旗（extracted_fields 中类型字段）
    try:
        extracted = json.loads(session.extracted_fields or "{}")
    except (json.JSONDecodeError, TypeError):
        extracted = {}
    red_flag = bool(extracted.get("red_flags"))

    message_items = [MessageItem(
        role=m.get("role", "assistant"),
        content=m.get("content", ""),
        tool_call_id=m.get("tool_call_id"),
        tool_name=m.get("tool_name"),
        skill_name=m.get("skill_name"),
        tool_status=m.get("tool_status"),
        tool_args=m.get("tool_args"),
        tool_result=m.get("tool_result"),
        message_id=m.get("message_id"),
        generation_status=m.get("generation_status"),
    ) for m in raw]

    # A background generation may outlive the browser SSE connection. Surface
    # its persisted partial text when history is reopened.
    rows = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id, ConversationMessage.role == "assistant")
        .order_by(ConversationMessage.created_at.desc())
    )
    latest_assistant = rows.scalars().first()
    if latest_assistant:
        payload = json.loads(latest_assistant.content_json or "{}")
        partial = payload.get("content", "")
        if latest_assistant.status in ("pending", "streaming", "failed"):
            message_items.append(MessageItem(
                role="assistant",
                content=partial,
                message_id=latest_assistant.id,
                generation_status=latest_assistant.status,
            ))
        elif message_items and message_items[-1].role == "assistant":
            message_items[-1].message_id = latest_assistant.id
            message_items[-1].generation_status = latest_assistant.status

    return SessionDetailResponse(
        session_id=session.id,
        status=session.status,
        messages=message_items,
        red_flag_detected=red_flag,
    )


@router.post("/{session_id}/messages", response_model=SessionMessageResponse)
@limiter.limit("20/minute")
async def send_message(
    request: Request,
    session_id: str,
    body: SendMessageRequest,
    _slot: None = Depends(_require_request_slot),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(ConsultationSession).where(
            ConsultationSession.id == session_id,
            ConsultationSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 幂等检查：如果提供了 client_request_id，检查是否已处理过
    if body.client_request_id:
        existing_msg = await db.execute(
            select(ConversationMessage).where(
                ConversationMessage.session_id == session_id,
                ConversationMessage.client_request_id == body.client_request_id,
            )
        )
        existing = existing_msg.scalar_one_or_none()
        if existing:
            # 返回已有的响应
            content = json.loads(existing.content_json)
            return SessionMessageResponse(
                status="completed",
                assistant_message=content.get("content", ""),
                structured_state={},
                red_flag_detected=False,
            )

    # 并发保护：使用 active_run_id 防止同一会话并发处理
    if session.active_run_id:
        # 检查是否超时（60 秒）
        from datetime import timedelta
        if session.updated_at and (datetime.now(timezone.utc) - session.updated_at) < timedelta(seconds=60):
            raise HTTPException(
                status_code=409,
                detail="会话正在处理中，请稍后再试",
            )
        # 超时，清除 active_run_id
        session.active_run_id = None

    # 设置 active_run_id
    session.active_run_id = str(uuid.uuid4())
    await db.flush()

    # 定义清理函数
    async def _clear_active_run():
        session.active_run_id = None
        await db.flush()

    messages: list[dict] = json.loads(session.raw_messages)

    # 统一上下文构建：并行查询技能、凭证、检验、体征
    from app.services.context_builder import build_consultation_context
    ctx = await build_consultation_context(
        db=db,
        user_id=user.id,
        body_content=body.content,
        body_media_urls=body.media_urls,
    )
    user_text = ctx.user_text
    user_content = ctx.user_content
    active_skills = ctx.active_skills
    latest_report = ctx.latest_report
    latest_vital = ctx.latest_vital

    messages.append({"role": "user", "content": user_content})

    # 安全围栏补强：最近高风险 IoT 事件可直接触发接管（防止仅靠文本触发漏检）
    if latest_vital and latest_vital.risk_level == "high":
        existing_ticket = await db.execute(
            select(HandoffTicket)
            .where(HandoffTicket.session_id == session.id)
            .where(HandoffTicket.status.in_(["pending", "processing"]))
            .order_by(HandoffTicket.created_at.desc())
        )
        if existing_ticket.scalar_one_or_none() is None:
            ticket = HandoffTicket(
                user_id=user.id,
                session_id=session.id,
                status="pending",
                risk_level="high",
                reason="IoT 高风险生命体征触发人工接管",
                brief=f"{latest_vital.metric}={latest_vital.value}{latest_vital.unit}",
                evidence=json.dumps(
                    [
                        f"source={latest_vital.source}",
                        f"metric={latest_vital.metric}",
                        f"value={latest_vital.value}{latest_vital.unit}",
                        f"measured_at={latest_vital.measured_at}",
                        f"event_id={latest_vital.id}",
                    ],
                    ensure_ascii=False,
                ),
            )
            db.add(ticket)
            db.add(
                AuditLog(
                    event_type="handoff.created.iot.message",
                    actor_id=user.id,
                    entity_type="handoff_ticket",
                    entity_id=ticket.id,
                    detail=json.dumps(
                        {"session_id": session.id, "iot_event_id": latest_vital.id},
                        ensure_ascii=False,
                    ),
                )
            )
            session.status = "HUMAN_HANDOFF_PENDING"
            assistant_content = _build_iot_emergency_message(latest_vital)
            messages.append({"role": "assistant", "content": assistant_content})
            session.raw_messages = json.dumps(messages, ensure_ascii=False)
            await db.flush()
            await db.commit()

            _queue_feishu_alert(
                user,
                reason="IoT 高风险生命体征触发人工接管",
                evidence=[f"{latest_vital.metric}={latest_vital.value}{latest_vital.unit}"],
                session_id=str(session.id),
            )

            return SessionMessageResponse(
                status=session.status,
                assistant_message=assistant_content,
                structured_state={},
                red_flag_detected=True,
            )

    # 只读工具意图不先等待语义风险模型；仍保留本地高风险关键词守卫。
    force_literature, literature_params = _should_force_literature_skill(user_text, active_skills)
    force_skill, extracted_drugs = _should_force_drug_skill(user_text, active_skills)
    force_profile, profile_params = _should_force_drug_profile(user_text, active_skills)
    if force_literature or force_skill or force_profile:
        risk_level, risk_evidence = evaluate_risk(user_text)
        risk_detail = {}
    else:
        risk_level, risk_evidence, risk_detail = await evaluate_risk_with_llm(messages, _get_user_llm_config(user))
    if risk_level == "high":
        risk_score = risk_detail.get("score", 0)
        risk_reason = risk_detail.get("reason", "")
        reason_text = f"风险评分 {risk_score}/10，触发人工接管" + (f"：{risk_reason}" if risk_reason else "")
        ticket = HandoffTicket(
            user_id=user.id,
            session_id=session.id,
            status="pending",
            risk_level="high",
            reason=reason_text,
            brief=user_text[:400],
            evidence=json.dumps(risk_evidence, ensure_ascii=False),
        )
        db.add(ticket)
        db.add(
            AuditLog(
                event_type="handoff.created",
                actor_id=user.id,
                entity_type="handoff_ticket",
                entity_id=ticket.id,
                detail=json.dumps({"session_id": session.id, "evidence": risk_evidence, "score_detail": risk_detail}, ensure_ascii=False),
            )
        )
        session.status = "HUMAN_HANDOFF_PENDING"
        assistant_content = emergency_reply()
        messages.append({"role": "assistant", "content": assistant_content})
        session.raw_messages = json.dumps(messages, ensure_ascii=False)
        await db.flush()
        await db.commit()

        _queue_feishu_alert(
            user,
            reason=reason_text,
            evidence=risk_evidence[:5] if risk_evidence else [],
            session_id=str(session.id),
        )

        return SessionMessageResponse(
            status=session.status,
            assistant_message=assistant_content,
            structured_state={},
            red_flag_detected=True,
        )

    if force_profile:
        result = await _execute_skill("drug-safety", "drug_profile", profile_params, active_skills, db, user.id)
        assistant_content = _format_skill_result("drug-safety", "drug_profile", result, active_skills)
        messages.append({"role": "assistant", "content": assistant_content})
        session.raw_messages = json.dumps(messages, ensure_ascii=False)
        await db.flush()
        await db.commit()
        return SessionMessageResponse(
            status=session.status, assistant_message=assistant_content,
            structured_state={}, red_flag_detected=False,
        )

    # 明确的文献检索请求直接调用 PubMed，避免初始模型超时导致工具根本未执行。
    if force_literature:
        literature_call_id = str(uuid.uuid4())
        literature_tool_name = next(
            (
                t.get("name")
                for skill in active_skills if skill.get("skill_id") == "medical-literature-review"
                for t in skill.get("tools", [])
                if t.get("name", "").endswith("__pubmed_search_articles")
            ),
            "pubmed-research__pubmed_search_articles",
        )
        t_start = time.time()
        result = await _execute_skill(
            "medical-literature-review", "search", literature_params, active_skills, db, user.id
        )
        latency_ms = int((time.time() - t_start) * 1000)
        await _record_tool_invocation(
            "medical-literature-review", literature_params, result, latency_ms, active_skills, db
        )
        assistant_content = _format_skill_result(
            "medical-literature-review", "search", result, active_skills
        )
        messages.extend([
            {
                "role": "tool", "content": "", "tool_call_id": literature_call_id,
                "tool_name": literature_tool_name, "skill_id": "medical-literature-review",
                "skill_name": "医学文献检索与综述", "tool_args": literature_params,
                "tool_status": "success" if result.get("success") else "failed",
                "tool_result": result,
            },
            {"role": "assistant", "content": assistant_content},
        ])
        session.raw_messages = json.dumps(messages, ensure_ascii=False)
        await db.flush()
        await db.commit()
        return SessionMessageResponse(
            status=session.status,
            assistant_message=assistant_content,
            structured_state={},
            red_flag_detected=False,
        )

    # 用户明确询问两药同用时，强制触发药物相互作用技能（不依赖 LLM 是否输出 invoke）
    if force_skill:
        t_start = time.time()
        result = await _execute_skill(
            skill_id="drug-safety",
            action="query_interactions",
            params={"drugs": extracted_drugs},
            active_skills=active_skills,
            db=db,
            user_id=user.id,
        )
        latency_ms = int((time.time() - t_start) * 1000)
        await _record_tool_invocation(
            skill_id="drug-safety",
            params={"drugs": extracted_drugs},
            result=result,
            latency_ms=latency_ms,
            active_skills=active_skills,
            db=db,
        )
        assistant_content = _format_skill_result(
            skill_id="drug-safety",
            action="query_interactions",
            result=result,
            active_skills=active_skills,
        )
        messages.append({"role": "assistant", "content": assistant_content})
        session.raw_messages = json.dumps(messages, ensure_ascii=False)
        await db.flush()
        await db.commit()
        return SessionMessageResponse(
            status=session.status,
            assistant_message=assistant_content,
            structured_state={},
            red_flag_detected=False,
        )

    # 兜底：用户明显要挂号/预约时，强制触发挂号预约技能（不依赖 LLM 是否输出 invoke 或 native function calling）
    force_reg, reg_params = _should_force_registration_skill(user_text, active_skills)
    if force_reg:
        t_start = time.time()
        result = await _execute_skill(
            skill_id="appointment-booking",
            action="query_schedule",
            params=reg_params,
            active_skills=active_skills,
            db=db,
            user_id=user.id,
        )
        latency_ms = int((time.time() - t_start) * 1000)
        await _record_tool_invocation(
            skill_id="appointment-booking",
            params=reg_params,
            result=result,
            latency_ms=latency_ms,
            active_skills=active_skills,
            db=db,
        )
        assistant_content = _format_skill_result(
            skill_id="appointment-booking",
            action="query_schedule",
            result=result,
            active_skills=active_skills,
        )
        messages.append({"role": "assistant", "content": assistant_content})
        session.raw_messages = json.dumps(messages, ensure_ascii=False)
        await db.flush()
        await db.commit()
        return SessionMessageResponse(
            status=session.status,
            assistant_message=assistant_content,
            structured_state={},
            red_flag_detected=False,
        )

    # Load existing extracted fields for context (e.g., summary continuation)
    existing_extracted = {}
    try:
        existing_extracted = json.loads(session.extracted_fields or "{}")
    except Exception:
        pass

    try:
        state = await asyncio.wait_for(
            run_consultation_turn(
                session_id=session_id,
                messages=messages,
                current_status=session.status,
                round_count=len([m for m in messages if m["role"] == "user"]),
                active_skills=active_skills,
                lang=body.lang,
                existing_extracted_fields=existing_extracted,
                user_llm_config=_get_user_llm_config(user),
            ),
            timeout=90,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="AI 响应超时，请重试")
    except Exception as e:
        err_name = e.__class__.__name__
        if "Authentication" in err_name or "401" in str(e):
            raise HTTPException(status_code=502, detail="AI 服务认证失败，请检查 OPENAI_API_KEY 配置")
        if "RateLimit" in err_name or "429" in str(e):
            raise HTTPException(status_code=429, detail="AI 服务请求过于频繁，请稍后重试")
        logger.exception(f"问诊处理失败: {e}")
        raise HTTPException(status_code=502, detail=f"AI 服务异常：{str(e)[:200]}")

    # Append AI reply — 先处理技能调用块，替换为真实执行结果
    assistant_content = state["latest_assistant_message"]
    assistant_content = await _process_skill_invocations(assistant_content, active_skills, db, user.id)
    messages.append({"role": "assistant", "content": assistant_content})

    # Persist
    session.raw_messages = json.dumps(messages, ensure_ascii=False)
    session.status = state["status"]
    if state.get("summary_json"):
        session.extracted_fields = json.dumps(state["summary_json"], ensure_ascii=False)
        session.triage_level = state["summary_json"].get("triage_level", "observe")
        session.summary = state["summary_json"].get("summary_text", "")

    await db.flush()
    await db.commit()

    # 清除 active_run_id
    await _clear_active_run()

    # Flush Langfuse traces for immediate visibility
    flush_langfuse()

    return SessionMessageResponse(
        status=state["status"],
        assistant_message=assistant_content,
        structured_state=state.get("extracted_fields") or {},
        red_flag_detected=state["red_flag_detected"],
    )


@router.post("/{session_id}/messages/stream")
@limiter.limit("20/minute")
async def send_message_stream(
    request: Request,
    session_id: str,
    body: SendMessageRequest,
    _slot: None = Depends(_require_request_slot),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """SSE 流式问诊端点。逐 token 输出 LLM 响应。"""
    import json as _json

    result = await db.execute(
        select(ConsultationSession).where(
            ConsultationSession.id == session_id,
            ConsultationSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    request_id = body.client_request_id or str(uuid.uuid4())
    existing_result = await db.execute(
        select(ConversationMessage).where(
            ConversationMessage.session_id == session_id,
            ConversationMessage.client_request_id == request_id,
        )
    )
    existing_request = existing_result.scalar_one_or_none()
    if existing_request:
        existing_payload = _json.loads(existing_request.content_json or "{}")
        if existing_request.status in ("pending", "streaming"):
            raise HTTPException(status_code=409, detail="该请求正在生成，请查询会话状态")
        if existing_request.status == "failed":
            raise HTTPException(status_code=409, detail=existing_payload.get("error") or "该请求上次生成失败")

        async def _replay_existing():
            content = existing_payload.get("content", "")
            async for token_event in _stream_text_events(content):
                yield token_event
            yield f"event: done\ndata: {_json.dumps({'message_id': existing_request.id, 'assistant_message': content, 'status': session.status, 'red_flag_detected': False, 'structured_state': {}}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            _replay_existing(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    messages: list[dict] = _json.loads(session.raw_messages)

    # 统一上下文构建
    from app.services.context_builder import build_consultation_context
    ctx = await build_consultation_context(
        db=db,
        user_id=user.id,
        body_content=body.content,
        body_media_urls=body.media_urls,
    )
    user_text = ctx.user_text
    user_content = ctx.user_content
    active_skills = ctx.active_skills
    latest_report = ctx.latest_report
    latest_vital = ctx.latest_vital

    messages.append({"role": "user", "content": user_content})

    # Reserve the idempotency key before any tool or model side effect.
    pending_msg = ConversationMessage(
        session_id=session_id, sequence=len(messages), role="assistant",
        content_json=_json.dumps({"content": ""}, ensure_ascii=False),
        status="pending", client_request_id=request_id,
    )
    db.add(pending_msg)
    try:
        await db.flush()
        await db.refresh(pending_msg)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="重复的客户端请求")
    pending_msg_id = pending_msg.id

    async def _complete_reserved_message(content: str, status: str = "completed") -> None:
        row = await db.get(ConversationMessage, pending_msg_id)
        if row:
            row.content_json = _json.dumps({"content": content}, ensure_ascii=False)
            row.status = status
            row.completed_at = utcnow()
            await db.commit()

    # IoT 高风险守卫
    if latest_vital and latest_vital.risk_level == "high":
        existing_ticket = await db.execute(
            select(HandoffTicket)
            .where(HandoffTicket.session_id == session.id)
            .where(HandoffTicket.status.in_(["pending", "processing"]))
            .order_by(HandoffTicket.created_at.desc())
        )
        if existing_ticket.scalar_one_or_none() is None:
            ticket = HandoffTicket(
                user_id=user.id,
                session_id=session.id,
                status="pending",
                risk_level="high",
                reason="IoT 高风险生命体征触发人工接管",
                brief=f"{latest_vital.metric}={latest_vital.value}{latest_vital.unit}",
                evidence=_json.dumps(
                    [f"source={latest_vital.source}", f"metric={latest_vital.metric}",
                     f"value={latest_vital.value}{latest_vital.unit}", f"measured_at={latest_vital.measured_at}"],
                    ensure_ascii=False,
                ),
            )
            db.add(ticket)
            session.status = "HUMAN_HANDOFF_PENDING"
            assistant_content = _build_iot_emergency_message(latest_vital)
            messages.append({"role": "assistant", "content": assistant_content})
            session.raw_messages = _json.dumps(messages, ensure_ascii=False)
            await db.flush()
            await db.commit()
            await _complete_reserved_message(assistant_content)

            _queue_feishu_alert(
                user,
                reason="IoT 高风险生命体征触发人工接管",
                evidence=[f"{latest_vital.metric}={latest_vital.value}{latest_vital.unit}"],
                session_id=str(session.id),
            )

            async def _early_sse():
                async for token_event in _stream_text_events(assistant_content):
                    yield token_event
                yield f"event: done\ndata: {_json.dumps({'assistant_message': assistant_content, 'status': session.status, 'red_flag_detected': True, 'structured_state': {}}, ensure_ascii=False)}\n\n"
            return StreamingResponse(_early_sse(), media_type="text/event-stream")

    # 只读工具意图不先等待语义风险模型；仍保留本地高风险关键词守卫。
    force_literature, literature_params = _should_force_literature_skill(user_text, active_skills)
    force_skill, extracted_drugs = _should_force_drug_skill(user_text, active_skills)
    force_profile, profile_params = _should_force_drug_profile(user_text, active_skills)
    if force_literature or force_skill or force_profile:
        risk_level_val, risk_evidence = evaluate_risk(user_text)
        risk_detail = {}
    else:
        risk_level_val, risk_evidence, risk_detail = await evaluate_risk_with_llm(messages, _get_user_llm_config(user))
    if risk_level_val == "high":
        risk_score = risk_detail.get("score", 0)
        risk_reason = risk_detail.get("reason", "")
        reason_text = f"风险评分 {risk_score}/10，触发人工接管" + (f"：{risk_reason}" if risk_reason else "")
        ticket = HandoffTicket(
            user_id=user.id, session_id=session.id, status="pending", risk_level="high",
            reason=reason_text, brief=user_text[:400],
            evidence=_json.dumps(risk_evidence, ensure_ascii=False),
        )
        db.add(ticket)
        session.status = "HUMAN_HANDOFF_PENDING"
        assistant_content = emergency_reply()
        messages.append({"role": "assistant", "content": assistant_content})
        session.raw_messages = _json.dumps(messages, ensure_ascii=False)
        await db.flush()
        await db.commit()
        await _complete_reserved_message(assistant_content)

        _queue_feishu_alert(
            user,
            reason=reason_text,
            evidence=risk_evidence[:5] if risk_evidence else [],
            session_id=str(session.id),
        )

        async def _early_sse_risk():
            async for token_event in _stream_text_events(assistant_content):
                yield token_event
            yield f"event: done\ndata: {_json.dumps({'assistant_message': assistant_content, 'status': session.status, 'red_flag_detected': True, 'structured_state': {}}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_early_sse_risk(), media_type="text/event-stream")

    if force_profile:
        result_profile = await _execute_skill(
            "drug-safety", "drug_profile", profile_params, active_skills, db, user.id
        )
        tool_runs = result_profile.get("tool_runs", [])
        await _record_workflow_runs("drug-safety", tool_runs, active_skills, db)
        assistant_content = _format_skill_result("drug-safety", "drug_profile", result_profile, active_skills)
        run_events = []
        for run in tool_runs:
            call_id = str(uuid.uuid4())
            run_events.append({**run, "call_id": call_id})
            messages.append({
                "role": "tool", "content": "", "tool_call_id": call_id,
                "tool_name": run["name"], "skill_id": "drug-safety",
                "skill_name": "OpenFDA 药品安全查询", "tool_args": run["args"],
                "tool_status": "success" if run["result"].get("status") == "success" else "failed",
                "tool_result": run["result"],
            })
        messages.append({"role": "assistant", "content": assistant_content})
        session.raw_messages = _json.dumps(messages, ensure_ascii=False)
        await db.flush()
        await db.commit()
        await _complete_reserved_message(assistant_content)

        async def _early_sse_profile():
            for run in run_events:
                base = {"call_id": run["call_id"], "name": run["name"], "skill_id": "drug-safety", "skill_name": "OpenFDA 药品安全查询"}
                yield f"event: tool_start\ndata: {_json.dumps({**base, 'args': run['args']}, ensure_ascii=False)}\n\n"
                yield f"event: tool_end\ndata: {_json.dumps({**base, 'result': run['result']}, ensure_ascii=False)}\n\n"
            async for token_event in _stream_text_events(assistant_content):
                yield token_event
            yield f"event: done\ndata: {_json.dumps({'assistant_message': assistant_content, 'status': session.status, 'red_flag_detected': False, 'structured_state': {}}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_early_sse_profile(), media_type="text/event-stream")

    # 明确的文献检索请求直接调用 PubMed。
    if force_literature:
        async def _early_sse_literature():
            event_queue: asyncio.Queue = asyncio.Queue()
            streamed_content = ""
            literature_skill_name = next(
                (s["name"] for s in active_skills if s["skill_id"] == "medical-literature-review"),
                "医学文献检索与综述",
            )

            async def _on_pubmed_event(event_type: str, payload: dict):
                await event_queue.put((event_type, payload))

            async def _run_pubmed_workflow():
                started_at = time.time()
                try:
                    result = await _execute_skill(
                        "medical-literature-review", "search", literature_params,
                        active_skills, db, user.id, event_callback=_on_pubmed_event,
                    )
                    await event_queue.put(("workflow_done", {
                        "result": result,
                        "latency_ms": int((time.time() - started_at) * 1000),
                    }))
                except BaseException as exc:
                    await event_queue.put(("workflow_error", {"error": str(exc)}))

            workflow_task = asyncio.create_task(_run_pubmed_workflow())
            result_literature = None
            latency_ms = 0
            try:
                while True:
                    event_type, payload = await event_queue.get()
                    if event_type == "workflow_error":
                        raise RuntimeError(payload["error"] or "PubMed 工作流异常")
                    if event_type == "workflow_done":
                        result_literature = payload["result"]
                        latency_ms = payload["latency_ms"]
                        break
                    if event_type == "content_delta":
                        delta = ""
                        if not streamed_content:
                            delta = f"\n\n---\n**✅ 【{literature_skill_name}】PubMed MCP 文献检索完成**"
                        delta += "\n" + "\n".join(
                            _format_pubmed_article(payload["article"], payload["index"])
                        )
                        streamed_content += delta
                        yield f"event: token\ndata: {_json.dumps({'content': delta}, ensure_ascii=False)}\n\n"
                        continue
                    base = {
                        "call_id": payload["call_id"], "name": payload["name"],
                        "skill_id": "medical-literature-review",
                        "skill_name": "PubMed 医学文献检索",
                    }
                    if event_type == "tool_start":
                        yield f"event: tool_start\ndata: {_json.dumps({**base, 'args': payload['args']}, ensure_ascii=False)}\n\n"
                    else:
                        yield f"event: tool_end\ndata: {_json.dumps({**base, 'result': payload['result']}, ensure_ascii=False)}\n\n"
                await workflow_task
            except Exception as exc:
                workflow_task.cancel()
                yield f"event: error\ndata: {_json.dumps({'message': f'PubMed 工作流失败：{str(exc)}'}, ensure_ascii=False)}\n\n"
                return

            if result_literature.get("tool_runs"):
                await _record_workflow_runs(
                    "medical-literature-review", result_literature["tool_runs"], active_skills, db
                )
            else:
                await _record_tool_invocation(
                    "medical-literature-review", literature_params, result_literature,
                    latency_ms, active_skills, db,
                )
            assistant_content = _format_skill_result(
                "medical-literature-review", "search", result_literature, active_skills
            )
            for run in result_literature.get("tool_runs", []):
                messages.append({
                    "role": "tool", "content": "", "tool_call_id": run["call_id"],
                    "tool_name": run["name"], "skill_id": "medical-literature-review",
                    "skill_name": "PubMed 医学文献检索", "tool_args": run["args"],
                    "tool_status": "success" if run["result"].get("status") == "success" else "failed",
                    "tool_result": run["result"],
                })
            messages.append({"role": "assistant", "content": assistant_content})
            session.raw_messages = _json.dumps(messages, ensure_ascii=False)
            await db.flush()
            await db.commit()
            await _complete_reserved_message(assistant_content)

            if streamed_content and not assistant_content.startswith(streamed_content):
                yield f"event: error\ndata: {_json.dumps({'message': 'PubMed 流式内容一致性校验失败'}, ensure_ascii=False)}\n\n"
                return
            remaining_content = assistant_content[len(streamed_content):]
            async for token_event in _stream_text_events(remaining_content):
                yield token_event
            yield f"event: done\ndata: {_json.dumps({'assistant_message': assistant_content, 'status': session.status, 'red_flag_detected': False, 'structured_state': {}}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_early_sse_literature(), media_type="text/event-stream")

    # 药物技能兜底
    if force_skill:
        drug_call_id = str(uuid.uuid4())
        drug_params = {"drugs": extracted_drugs}
        drug_tool_name = "check_drug_interaction"
        t_start = time.time()
        result_skill = await _execute_skill(
            skill_id="drug-safety", action="query_interactions",
            params=drug_params, active_skills=active_skills, db=db, user_id=user.id,
        )
        latency_ms = int((time.time() - t_start) * 1000)
        await _record_tool_invocation("drug-safety", drug_params, result_skill, latency_ms, active_skills, db)
        assistant_content = _format_skill_result("drug-safety", "query_interactions", result_skill, active_skills)
        messages.extend([
            {
                "role": "tool", "content": "", "tool_call_id": drug_call_id,
                "tool_name": drug_tool_name, "skill_id": "drug-safety",
                "skill_name": "用药安全检查", "tool_args": drug_params,
                "tool_status": "success" if result_skill.get("success") else "failed",
                "tool_result": result_skill,
            },
            {"role": "assistant", "content": assistant_content},
        ])
        session.raw_messages = _json.dumps(messages, ensure_ascii=False)
        await db.flush()
        await db.commit()
        await _complete_reserved_message(assistant_content)

        async def _early_sse_drug():
            yield f"event: tool_start\ndata: {_json.dumps({'call_id': drug_call_id, 'name': drug_tool_name, 'skill_id': 'drug-safety', 'skill_name': '用药安全检查', 'args': drug_params}, ensure_ascii=False)}\n\n"
            yield f"event: tool_end\ndata: {_json.dumps({'call_id': drug_call_id, 'name': drug_tool_name, 'skill_id': 'drug-safety', 'skill_name': '用药安全检查', 'result': result_skill}, ensure_ascii=False)}\n\n"
            async for token_event in _stream_text_events(assistant_content):
                yield token_event
            yield f"event: done\ndata: {_json.dumps({'assistant_message': assistant_content, 'status': session.status, 'red_flag_detected': False, 'structured_state': {}}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_early_sse_drug(), media_type="text/event-stream")

    # 挂号预约技能兜底
    force_reg, reg_params = _should_force_registration_skill(user_text, active_skills)
    if force_reg:
        t_start = time.time()
        result_reg = await _execute_skill(
            skill_id="appointment-booking", action="query_schedule",
            params=reg_params, active_skills=active_skills, db=db, user_id=user.id,
        )
        latency_ms = int((time.time() - t_start) * 1000)
        await _record_tool_invocation("appointment-booking", reg_params, result_reg, latency_ms, active_skills, db)
        assistant_content = _format_skill_result("appointment-booking", "query_schedule", result_reg, active_skills)
        messages.append({"role": "assistant", "content": assistant_content})
        session.raw_messages = _json.dumps(messages, ensure_ascii=False)
        await db.flush()
        await db.commit()
        await _complete_reserved_message(assistant_content)

        async def _early_sse_reg():
            async for token_event in _stream_text_events(assistant_content):
                yield token_event
            yield f"event: done\ndata: {_json.dumps({'assistant_message': assistant_content, 'status': session.status, 'red_flag_detected': False, 'structured_state': {}}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_early_sse_reg(), media_type="text/event-stream")

    # ── 主路径：SSE 流式输出 ──
    # Number of completed turns before the user message just appended. This
    # keeps select_next_agent's first-turn contract (round_count == 0).
    round_count = max(0, len([m for m in messages if m["role"] == "user"]) - 1)

    # Load existing extracted fields for context (e.g., summary continuation)
    existing_extracted = {}
    try:
        existing_extracted = _json.loads(session.extracted_fields or "{}")
    except Exception:
        pass

    # Persist the user turn before starting generation. The generation runs in
    # an independent DB session and therefore survives browser navigation.
    run_id = str(uuid.uuid4())
    stale_before = utcnow() - timedelta(seconds=120)
    lock_result = await db.execute(
        update(ConsultationSession)
        .where(
            ConsultationSession.id == session_id,
            ConsultationSession.user_id == user.id,
            or_(
                ConsultationSession.active_run_id.is_(None),
                ConsultationSession.active_run_heartbeat_at < stale_before,
                ConsultationSession.active_run_heartbeat_at.is_(None),
            ),
        )
        .values(active_run_id=run_id, active_run_heartbeat_at=utcnow())
    )
    if lock_result.rowcount != 1:
        await db.rollback()
        reserved = await db.get(ConversationMessage, pending_msg_id)
        if reserved:
            reserved.status = "failed"
            reserved.content_json = _json.dumps({
                "content": "会话正在生成另一条回答",
                "error": "session_busy",
            }, ensure_ascii=False)
            reserved.completed_at = utcnow()
            await db.commit()
        raise HTTPException(status_code=409, detail="会话正在生成回答，请等待完成")

    from app.services.clinical_memory import update_clinical_memory
    try:
        memory = _json.loads(session.clinical_memory or "{}")
    except (TypeError, _json.JSONDecodeError):
        memory = {}
    memory = update_clinical_memory(memory, user_text, request_id)
    session.clinical_memory = _json.dumps(memory, ensure_ascii=False)
    existing_extracted = {**memory, **existing_extracted}
    session.raw_messages = _json.dumps(messages, ensure_ascii=False)
    await db.commit()
    stream_queue: asyncio.Queue = asyncio.Queue()

    async def _background_generate() -> None:
        full_content = ""
        persisted_length = 0
        last_persisted_at = time.monotonic()
        tool_rows: dict[str, ConversationMessage] = {}
        async with AsyncSessionLocal() as bg_db:
            bg_session = await bg_db.get(ConsultationSession, session_id)
            bg_pending = await bg_db.get(ConversationMessage, pending_msg_id)
            if not bg_session or not bg_pending:
                await stream_queue.put(("error", {"message": "生成任务不存在"}))
                return
            try:
                bg_pending.status = "streaming"
                await bg_db.commit()
                async for event_type, payload in run_consultation_turn_stream(
                    session_id=session_id,
                    messages=messages,
                    current_status=bg_session.status,
                    round_count=round_count,
                    active_skills=active_skills,
                    lang=body.lang,
                    existing_extracted_fields=existing_extracted,
                    user_llm_config=_get_user_llm_config(user),
                    db_session=bg_db,
                    user_id=user.id,
                ):
                    if event_type == "token":
                        full_content += payload
                        await stream_queue.put(("token", payload))
                        now = time.monotonic()
                        if len(full_content) - persisted_length >= 256 or now - last_persisted_at >= 0.75:
                            bg_pending.content_json = _json.dumps({"content": full_content}, ensure_ascii=False)
                            bg_session.active_run_heartbeat_at = utcnow()
                            await bg_db.commit()
                            persisted_length = len(full_content)
                            last_persisted_at = now
                    elif event_type == "tool_start":
                        await stream_queue.put(("tool_start", payload))
                        raw = _json.loads(bg_session.raw_messages or "[]")
                        tool_entry = {
                            "role": "tool", "content": "", "message_id": str(uuid.uuid4()),
                            "tool_call_id": payload.get("call_id"), "tool_name": payload.get("name"),
                            "skill_name": payload.get("skill_name"), "tool_status": "running",
                            "tool_args": payload.get("args", {}),
                        }
                        raw.append(tool_entry)
                        bg_session.raw_messages = _json.dumps(raw, ensure_ascii=False)
                        tool_row = ConversationMessage(
                            id=tool_entry["message_id"], session_id=session_id, sequence=len(raw),
                            parent_message_id=pending_msg_id, role="tool",
                            content_json=_json.dumps(tool_entry, ensure_ascii=False), status="streaming",
                        )
                        bg_db.add(tool_row)
                        tool_rows[payload.get("call_id", "")] = tool_row
                        await bg_db.commit()
                    elif event_type == "tool_end":
                        await stream_queue.put(("tool_end", payload))
                        call_id = payload.get("call_id", "")
                        result_data = payload.get("result", {})
                        failed = result_data.get("status") == "failed" or bool(result_data.get("error"))
                        raw = _json.loads(bg_session.raw_messages or "[]")
                        for item in reversed(raw):
                            if item.get("role") == "tool" and item.get("tool_call_id") == call_id:
                                item["tool_status"] = "failed" if failed else "success"
                                item["tool_result"] = result_data
                                break
                        bg_session.raw_messages = _json.dumps(raw, ensure_ascii=False)
                        tool_row = tool_rows.get(call_id)
                        if tool_row:
                            tool_row.content_json = _json.dumps(next(
                                (item for item in reversed(raw) if item.get("tool_call_id") == call_id), {}
                            ), ensure_ascii=False)
                            tool_row.status = "failed" if failed else "completed"
                            tool_row.completed_at = utcnow()
                        await bg_db.commit()
                    elif event_type == "state":
                        state = payload
                        processed_content = await _process_skill_invocations(
                            state["latest_assistant_message"], active_skills, bg_db, user.id
                        )
                        raw = _json.loads(bg_session.raw_messages or "[]")
                        raw.append({
                            "role": "assistant", "content": processed_content,
                            "message_id": pending_msg_id, "generation_status": "completed",
                        })
                        bg_session.raw_messages = _json.dumps(raw, ensure_ascii=False)
                        bg_session.status = state["status"]
                        if state.get("summary_json"):
                            from app.services.clinical_memory import merge_summary
                            current_memory = _json.loads(bg_session.clinical_memory or "{}")
                            bg_session.clinical_memory = _json.dumps(
                                merge_summary(current_memory, state["summary_json"]), ensure_ascii=False
                            )
                            bg_session.extracted_fields = _json.dumps(state["summary_json"], ensure_ascii=False)
                            bg_session.triage_level = state["summary_json"].get("triage_level", "observe")
                            bg_session.summary = state["summary_json"].get("summary_text", "")
                        bg_pending.content_json = _json.dumps({"content": processed_content}, ensure_ascii=False)
                        bg_pending.status = "completed"
                        bg_pending.completed_at = utcnow()
                        if bg_session.active_run_id == run_id:
                            bg_session.active_run_id = None
                            bg_session.active_run_heartbeat_at = None
                        await bg_db.commit()
                        flush_langfuse()
                        await stream_queue.put(("done", {
                            "message_id": bg_pending.id,
                            "assistant_message": processed_content,
                            "status": bg_session.status,
                            "red_flag_detected": state.get("red_flag_detected", False),
                            "structured_state": state.get("extracted_fields") or {},
                        }))
            except Exception as exc:
                logger.exception(
                    "问诊后台生成失败 session_id=%s message_id=%s",
                    session_id,
                    pending_msg_id,
                )
                await bg_db.rollback()
                bg_pending = await bg_db.get(ConversationMessage, pending_msg_id)
                error_text = str(exc).strip() or exc.__class__.__name__
                if full_content.strip():
                    persisted_error_content = (
                        full_content.rstrip()
                        + "\n\n（本次回答传输中断，以上内容可能不完整，请重新发送问题。）"
                    )
                elif body.lang == "en":
                    persisted_error_content = "The AI service is temporarily unavailable. Please retry this message."
                else:
                    persisted_error_content = "AI 服务暂时不稳定，请重新发送本条消息。"
                if bg_pending:
                    bg_pending.status = "failed"
                    bg_pending.content_json = _json.dumps(
                        {"content": persisted_error_content, "error": error_text},
                        ensure_ascii=False,
                    )
                    if bg_session and bg_session.active_run_id == run_id:
                        bg_session.active_run_id = None
                        bg_session.active_run_heartbeat_at = None
                    await bg_db.commit()
                event_name = "incomplete" if isinstance(exc, OutputLimitExceeded) else "error"
                await stream_queue.put((event_name, {
                    "message_id": pending_msg_id,
                    "message": persisted_error_content,
                }))

    task = asyncio.create_task(_background_generate())
    _background_generation_tasks.add(task)
    task.add_done_callback(_background_generation_tasks.discard)

    async def _sse_generator():
        while True:
            try:
                event_type, payload = await asyncio.wait_for(stream_queue.get(), timeout=15)
            except asyncio.TimeoutError:
                # Keep reverse proxies and browsers from treating a slow first
                # model token as an idle/dead SSE connection.
                yield ": keepalive\n\n"
                continue
            yield f"event: {event_type}\ndata: {_json.dumps(payload if isinstance(payload, dict) else {'content': payload}, ensure_ascii=False)}\n\n"
            if event_type in ("done", "error", "incomplete"):
                return

    return StreamingResponse(
        _sse_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/{session_id}/summary", response_model=SessionSummaryResponse)
async def get_summary(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(ConsultationSession).where(
            ConsultationSession.id == session_id,
            ConsultationSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    try:
        extracted = json.loads(session.extracted_fields or "{}")
    except (json.JSONDecodeError, TypeError):
        extracted = {}
    ready = session.status in ("SUMMARY_READY", "EVENT_CARD_READY")

    return SessionSummaryResponse(
        session_id=session.id,
        status=session.status,
        summary=session.summary,
        triage_level=session.triage_level,
        extracted_fields=extracted,
        ready_for_event_card=ready,
    )


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(ConsultationSession).where(
            ConsultationSession.id == session_id,
            ConsultationSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    # 先删除子记录，避免外键约束冲突
    await db.execute(delete(ConversationMessage).where(ConversationMessage.session_id == session_id))
    await db.execute(delete(HealthEvent).where(HealthEvent.source_session_id == session_id))
    await db.execute(delete(HandoffTicket).where(HandoffTicket.session_id == session_id))
    # 清理 PostgreSQL checkpoint 数据
    await cleanup_checkpoint(session_id)
    await db.delete(session)
    await db.commit()


@router.post("/{session_id}/event-card", response_model=EventCardResponse)
async def generate_event_card(
    session_id: str,
    body: CreateEventCardRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(ConsultationSession).where(
            ConsultationSession.id == session_id,
            ConsultationSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    card = body.event_card

    event = HealthEvent(
        user_id=user.id,
        source_session_id=session_id,
        status="CREATED",
        chief_complaint=card.chief_complaint,
        symptom_summary=json.dumps(card.symptom_summary, ensure_ascii=False),
        duration=card.duration,
        severity=card.severity,
        confirmed_points=json.dumps(card.confirmed_points, ensure_ascii=False),
        uncertain_points=json.dumps(card.uncertain_points, ensure_ascii=False),
        red_flags=json.dumps(card.red_flags, ensure_ascii=False),
        candidate_conditions=json.dumps(
            [c.model_dump() for c in card.candidate_conditions], ensure_ascii=False
        ),
        triage_level=card.triage_level,
        recommended_department=card.recommended_department,
        visit_preparation=json.dumps(card.visit_preparation, ensure_ascii=False),
        care_todos=json.dumps(card.care_todos, ensure_ascii=False),
        medication_reminder_suggestion=json.dumps(
            card.medication_reminder_suggestion, ensure_ascii=False
        ),
        followup_reminder_suggestion=json.dumps(
            card.followup_reminder_suggestion, ensure_ascii=False
        ),
        record_update_suggestion=card.record_update_suggestion,
        insurance_material_suggestion=json.dumps(
            card.insurance_material_suggestion, ensure_ascii=False
        ),
    )
    db.add(event)
    session.status = "EVENT_CARD_READY"
    await db.flush()
    await db.refresh(event)

    return EventCardResponse(
        event_id=event.id,
        status=event.status,
        chief_complaint=event.chief_complaint,
        triage_level=event.triage_level,
        recommended_department=event.recommended_department,
        created_at=event.created_at,
    )


@router.get("/context/patient")
async def get_patient_context(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """获取患者上下文信息（记忆事实、检验摘要、穿戴数据），用于右侧信息面板展示。"""
    # 并行查询
    memory_q = db.execute(
        select(MemoryFact)
        .where(MemoryFact.user_id == user.id, MemoryFact.status == "confirmed")
        .order_by(MemoryFact.confidence.desc())
        .limit(20)
    )
    report_q = db.execute(
        select(LabReport).where(LabReport.user_id == user.id).order_by(LabReport.created_at.desc()).limit(1)
    )
    vital_q = db.execute(
        select(VitalStreamEvent).where(VitalStreamEvent.user_id == user.id).order_by(VitalStreamEvent.created_at.desc()).limit(5)
    )
    memory_res, report_res, vital_res = await asyncio.gather(memory_q, report_q, vital_q)

    # 记忆事实
    memory_facts = []
    for f in memory_res.scalars().all():
        try:
            val = json.loads(f.value_json)
            text = val.get("text", str(val))
        except Exception:
            text = f.value_json
        memory_facts.append({
            "id": f.id,
            "type": f.fact_type,
            "text": text,
            "confidence": f.confidence,
        })

    # 检验报告
    report = report_res.scalars().first()
    report_data = None
    if report:
        report_data = {
            "id": report.id,
            "summary": report.summary or "",
            "created_at": report.created_at.isoformat() if report.created_at else None,
        }

    # 穿戴数据
    vitals = []
    for v in vital_res.scalars().all():
        vitals.append({
            "id": v.id,
            "metric": v.metric,
            "value": v.value,
            "unit": v.unit or "",
            "risk_level": v.risk_level or "normal",
            "created_at": v.created_at.isoformat() if v.created_at else None,
        })

    return {
        "memory_facts": memory_facts,
        "latest_report": report_data,
        "vitals": vitals,
    }
