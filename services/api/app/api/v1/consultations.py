"""健康问诊工作区 API"""
import asyncio
import json
import re
import time
import uuid
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.concurrency import get_request_semaphore
from sqlalchemy import select
from app.api.deps.auth import get_current_user_required
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.models import (
    ConsultationSession,
    AuditLog,
    HandoffTicket,
    HealthEvent,
    LabReport,
    SkillPackage,
    ToolInvocationLog,
    User,
    UserOAuthCredential,
    VitalStreamEvent,
)
from app.schemas.schemas import (
    CreateSessionRequest, SessionResponse,
    SendMessageRequest, SessionMessageResponse,
    SessionSummaryResponse,
    SessionDetailResponse, MessageItem,
    CreateEventCardRequest, EventCardResponse,
)
from app.orchestrators.consultation import run_consultation_turn, run_consultation_turn_stream, detect_red_flags
from app.services.registration import RegistrationService
from app.services.drug_interaction import query_drug_interactions, ZH_TO_EN
from app.services.risk_guardrail import emergency_reply, evaluate_risk
from app.services.tool_registry import execute_tool_call
from app.core.observability import flush_langfuse

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
    不依赖 active_skills 中是否注册了 drug-interaction，直接可用。
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
    active_skills: list[dict], db: AsyncSession, user_id: str
) -> dict:
    """统一技能执行入口：appointment-booking 走真实 DB，其余保留实用 mock。"""

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

    # ── 药物相互作用：调用 NIH RxNav 公开 API ────────────────────────────────────
    if skill_id == "drug-interaction":
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
        return await query_drug_interactions(drugs)

    # ── 健康任务同步：实用 mock（待接入飞书/Notion API）─────────────────────────────
    if skill_id == "task-sync":
        platform = params.get("platform") or "飞书"
        title = params.get("title") or params.get("task") or "健康随访任务"
        return {
            "success": True,
            "message": f"任务已同步到{platform}",
            "data": {"platform": platform, "task_title": title, "task_id": "TASK-20260420-001"},
        }

    # ── 跨 App 智能体：实用 mock（待接入 AutoGLM）──────────────────────────────────
    if skill_id == "cross-app-agent":
        app_name = params.get("app") or "医保服务"
        return {
            "success": True,
            "message": "跨应用操作已完成",
            "data": {"app": app_name, "steps_completed": 3, "status": "操作成功"},
        }

    return {"success": False, "message": f"技能 {skill_id} 暂未实现", "data": {}}


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

    elif skill_id == "drug-interaction":
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
            tool_name=next((s["name"] for s in active_skills if s["skill_id"] == skill_id), skill_id),
            request_json=json.dumps(params, ensure_ascii=False),
            response_json=json.dumps(result.get("data", {}), ensure_ascii=False),
            latency_ms=latency_ms,
            result_status="success" if result.get("success") else "failed",
            error_reason="" if result.get("success") else result.get("message", ""),
        )
        db.add(log)
    except Exception:
        pass


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
        except (json.JSONDecodeError, Exception):
            pass  # 解析失败保留原块

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
        .order_by(ConsultationSession.created_at.desc())
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
                if isinstance(m, dict) and m.get("role") == "assistant":
                    for match in _skill_tag_re.findall(m.get("content", "")):
                        if match not in seen:
                            seen.add(match)
                            skill_tags.append(match)
        except Exception:
            pass
        items.append(SessionResponse(
            session_id=s.id,
            status=s.status,
            created_at=s.created_at,
            chief_complaint=extracted.get("chief_complaint") or s.summary or "",
            triage_level=s.triage_level or "",
            skill_tags=skill_tags,
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

    return SessionDetailResponse(
        session_id=session.id,
        status=session.status,
        messages=[MessageItem(role=m["role"], content=m["content"]) for m in raw],
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

    messages: list[dict] = json.loads(session.raw_messages)

    # 多模态内容处理：content 可以是 str 或 list[ContentPart]
    is_multimodal = isinstance(body.content, list)
    if is_multimodal:
        # 提取文本部分用于风险评估和 RAG
        text_parts = [p.text for p in body.content if p.type == "text" and p.text]
        user_text = " ".join(text_parts)
        # 构建 OpenAI Vision 格式的多模态内容
        multimodal_content = []
        for part in body.content:
            if part.type == "text":
                multimodal_content.append({"type": "text", "text": part.text or ""})
            elif part.type == "image_url" and part.image_url:
                multimodal_content.append({"type": "image_url", "image_url": part.image_url})
            elif part.type == "video_url" and part.video_url:
                multimodal_content.append({"type": "video_url", "video_url": part.video_url})
        # 添加已上传的媒体 URL
        if body.media_urls:
            for url in body.media_urls:
                if any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    multimodal_content.append({"type": "image_url", "image_url": {"url": url}})
                elif any(ext in url.lower() for ext in [".mp4", ".avi", ".mov", ".mkv", ".webm"]):
                    multimodal_content.append({"type": "video_url", "video_url": {"url": url}})
        user_content = multimodal_content
    else:
        user_text = body.content
        user_content = body.content

    # 并行查询：活跃技能、用户凭证、最近检验、最近体征
    skill_q = db.execute(select(SkillPackage).where(SkillPackage.status == "ACTIVE"))
    cred_q = db.execute(select(UserOAuthCredential).where(UserOAuthCredential.user_id == user.id))
    report_q = db.execute(
        select(LabReport).where(LabReport.user_id == user.id).order_by(LabReport.created_at.desc())
    )
    vital_q = db.execute(
        select(VitalStreamEvent)
        .where(VitalStreamEvent.user_id == user.id)
        .order_by(VitalStreamEvent.created_at.desc())
    )
    skill_result, cred_result, latest_report_res, latest_vital_res = await asyncio.gather(
        skill_q, cred_q, report_q, vital_q
    )
    skill_rows = skill_result.scalars().all()
    connected_providers = {c.provider for c in cred_result.scalars().all()}

    active_skills = [
        {
            "skill_id": s.skill_id,
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "trigger_examples": json.loads(s.trigger_examples or "[]"),
            "confirm_required": s.confirm_required,
            "tools": json.loads(s.tools or "[]"),
        }
        for s in skill_rows
        if (
            s.source_type != "plugin"
            or json.loads(s.manifest_json or "{}").get("auth_type", "none") == "none"
            or json.loads(s.manifest_json or "{}").get("provider") in connected_providers
        )
    ]
    # 注入 OCR 和 IoT 的最近上下文，帮助问诊推理
    latest_report = latest_report_res.scalars().first()
    if latest_report and latest_report.summary:
        user_text += f"\n[最近检验摘要] {latest_report.summary}"

    latest_vital = latest_vital_res.scalars().first()
    if latest_vital:
        user_text += (
            f"\n[最近穿戴设备数据] {latest_vital.metric}={latest_vital.value}{latest_vital.unit} "
            f"risk={latest_vital.risk_level}"
        )

    # 多模态消息：将上下文追加到文本部分
    if is_multimodal:
        # 找到最后一个 text 类型的 part 并追加上下文
        context_suffix = ""
        if latest_report and latest_report.summary:
            context_suffix += f"\n[最近检验摘要] {latest_report.summary}"
        if latest_vital:
            context_suffix += (
                f"\n[最近穿戴设备数据] {latest_vital.metric}={latest_vital.value}{latest_vital.unit} "
                f"risk={latest_vital.risk_level}"
            )
        if context_suffix:
            # 在多模态内容末尾追加上下文文本
            multimodal_content.append({"type": "text", "text": context_suffix})
        user_content = multimodal_content
    else:
        # 非多模态：user_text 已包含上下文
        user_content = user_text

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
            return SessionMessageResponse(
                status=session.status,
                assistant_message=assistant_content,
                structured_state={},
                red_flag_detected=True,
            )

    # 安全围栏：高风险直接转人工并挂起
    risk_level, risk_evidence = evaluate_risk(user_text)
    if risk_level == "high":
        ticket = HandoffTicket(
            user_id=user.id,
            session_id=session.id,
            status="pending",
            risk_level="high",
            reason="命中高危语义规则，触发人工接管",
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
                detail=json.dumps({"session_id": session.id, "evidence": risk_evidence}, ensure_ascii=False),
            )
        )
        session.status = "HUMAN_HANDOFF_PENDING"
        assistant_content = emergency_reply()
        messages.append({"role": "assistant", "content": assistant_content})
        session.raw_messages = json.dumps(messages, ensure_ascii=False)
        await db.flush()
        await db.commit()
        return SessionMessageResponse(
            status=session.status,
            assistant_message=assistant_content,
            structured_state={},
            red_flag_detected=True,
        )

    # 兜底：用户明确询问两药同用时，强制触发药物相互作用技能（不依赖 LLM 是否输出 invoke）
    force_skill, extracted_drugs = _should_force_drug_skill(user_text, active_skills)
    if force_skill:
        t_start = time.time()
        result = await _execute_skill(
            skill_id="drug-interaction",
            action="query_interactions",
            params={"drugs": extracted_drugs},
            active_skills=active_skills,
            db=db,
            user_id=user.id,
        )
        latency_ms = int((time.time() - t_start) * 1000)
        await _record_tool_invocation(
            skill_id="drug-interaction",
            params={"drugs": extracted_drugs},
            result=result,
            latency_ms=latency_ms,
            active_skills=active_skills,
            db=db,
        )
        assistant_content = _format_skill_result(
            skill_id="drug-interaction",
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
            ),
            timeout=45,
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

    messages: list[dict] = _json.loads(session.raw_messages)

    # 多模态内容处理
    is_multimodal = isinstance(body.content, list)
    if is_multimodal:
        text_parts = [p.text for p in body.content if p.type == "text" and p.text]
        user_text = " ".join(text_parts)
        multimodal_content = []
        for part in body.content:
            if part.type == "text":
                multimodal_content.append({"type": "text", "text": part.text or ""})
            elif part.type == "image_url" and part.image_url:
                multimodal_content.append({"type": "image_url", "image_url": part.image_url})
            elif part.type == "video_url" and part.video_url:
                multimodal_content.append({"type": "video_url", "video_url": part.video_url})
        if body.media_urls:
            for url in body.media_urls:
                if any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    multimodal_content.append({"type": "image_url", "image_url": {"url": url}})
                elif any(ext in url.lower() for ext in [".mp4", ".avi", ".mov", ".mkv", ".webm"]):
                    multimodal_content.append({"type": "video_url", "video_url": {"url": url}})
        user_content = multimodal_content
    else:
        user_text = body.content
        user_content = body.content

    # 并行查询：活跃技能、用户凭证、最近检验、最近体征
    skill_q = db.execute(select(SkillPackage).where(SkillPackage.status == "ACTIVE"))
    cred_q = db.execute(select(UserOAuthCredential).where(UserOAuthCredential.user_id == user.id))
    report_q = db.execute(
        select(LabReport).where(LabReport.user_id == user.id).order_by(LabReport.created_at.desc())
    )
    vital_q = db.execute(
        select(VitalStreamEvent)
        .where(VitalStreamEvent.user_id == user.id)
        .order_by(VitalStreamEvent.created_at.desc())
    )
    skill_result, cred_result, latest_report_res, latest_vital_res = await asyncio.gather(
        skill_q, cred_q, report_q, vital_q
    )
    skill_rows = skill_result.scalars().all()
    connected_providers = {c.provider for c in cred_result.scalars().all()}

    active_skills = [
        {
            "skill_id": s.skill_id,
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "trigger_examples": _json.loads(s.trigger_examples or "[]"),
            "confirm_required": s.confirm_required,
            "tools": _json.loads(s.tools or "[]"),
        }
        for s in skill_rows
        if (
            s.source_type != "plugin"
            or _json.loads(s.manifest_json or "{}").get("auth_type", "none") == "none"
            or _json.loads(s.manifest_json or "{}").get("provider") in connected_providers
        )
    ]

    # 注入上下文
    latest_report = latest_report_res.scalars().first()
    if latest_report and latest_report.summary:
        user_text += f"\n[最近检验摘要] {latest_report.summary}"

    latest_vital = latest_vital_res.scalars().first()
    if latest_vital:
        user_text += (
            f"\n[最近穿戴设备数据] {latest_vital.metric}={latest_vital.value}{latest_vital.unit} "
            f"risk={latest_vital.risk_level}"
        )

    if is_multimodal:
        context_suffix = ""
        if latest_report and latest_report.summary:
            context_suffix += f"\n[最近检验摘要] {latest_report.summary}"
        if latest_vital:
            context_suffix += (
                f"\n[最近穿戴设备数据] {latest_vital.metric}={latest_vital.value}{latest_vital.unit} "
                f"risk={latest_vital.risk_level}"
            )
        if context_suffix:
            multimodal_content.append({"type": "text", "text": context_suffix})
        user_content = multimodal_content
    else:
        user_content = user_text

    messages.append({"role": "user", "content": user_content})

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

            async def _early_sse():
                yield f"event: done\ndata: {_json.dumps({'assistant_message': assistant_content, 'status': session.status, 'red_flag_detected': True, 'structured_state': {}}, ensure_ascii=False)}\n\n"
            return StreamingResponse(_early_sse(), media_type="text/event-stream")

    # 文本高风险守卫
    risk_level_val, risk_evidence = evaluate_risk(user_text)
    if risk_level_val == "high":
        ticket = HandoffTicket(
            user_id=user.id, session_id=session.id, status="pending", risk_level="high",
            reason="命中高危语义规则，触发人工接管", brief=user_text[:400],
            evidence=_json.dumps(risk_evidence, ensure_ascii=False),
        )
        db.add(ticket)
        session.status = "HUMAN_HANDOFF_PENDING"
        assistant_content = emergency_reply()
        messages.append({"role": "assistant", "content": assistant_content})
        session.raw_messages = _json.dumps(messages, ensure_ascii=False)
        await db.flush()
        await db.commit()

        async def _early_sse_risk():
            yield f"event: done\ndata: {_json.dumps({'assistant_message': assistant_content, 'status': session.status, 'red_flag_detected': True, 'structured_state': {}}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_early_sse_risk(), media_type="text/event-stream")

    # 药物技能兜底
    force_skill, extracted_drugs = _should_force_drug_skill(user_text, active_skills)
    if force_skill:
        t_start = time.time()
        result_skill = await _execute_skill(
            skill_id="drug-interaction", action="query_interactions",
            params={"drugs": extracted_drugs}, active_skills=active_skills, db=db, user_id=user.id,
        )
        latency_ms = int((time.time() - t_start) * 1000)
        await _record_tool_invocation("drug-interaction", {"drugs": extracted_drugs}, result_skill, latency_ms, active_skills, db)
        assistant_content = _format_skill_result("drug-interaction", "query_interactions", result_skill, active_skills)
        messages.append({"role": "assistant", "content": assistant_content})
        session.raw_messages = _json.dumps(messages, ensure_ascii=False)
        await db.flush()
        await db.commit()

        async def _early_sse_drug():
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

        async def _early_sse_reg():
            yield f"event: done\ndata: {_json.dumps({'assistant_message': assistant_content, 'status': session.status, 'red_flag_detected': False, 'structured_state': {}}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_early_sse_reg(), media_type="text/event-stream")

    # ── 主路径：SSE 流式输出 ──
    round_count = len([m for m in messages if m["role"] == "user"])

    # Load existing extracted fields for context (e.g., summary continuation)
    existing_extracted = {}
    try:
        existing_extracted = _json.loads(session.extracted_fields or "{}")
    except Exception:
        pass

    async def _sse_generator():
        full_content = ""
        try:
            async for event_type, payload in run_consultation_turn_stream(
                session_id=session_id,
                messages=messages,
                current_status=session.status,
                round_count=round_count,
                active_skills=active_skills,
                lang=body.lang,
                existing_extracted_fields=existing_extracted,
            ):
                if event_type == "token":
                    full_content += payload
                    yield f"event: token\ndata: {_json.dumps({'content': payload}, ensure_ascii=False)}\n\n"
                elif event_type == "tool_start":
                    yield f"event: tool_start\ndata: {_json.dumps(payload, ensure_ascii=False)}\n\n"
                elif event_type == "tool_end":
                    yield f"event: tool_end\ndata: {_json.dumps(payload, ensure_ascii=False)}\n\n"
                elif event_type == "state":
                    state = payload
                    # Process legacy skill invocations (fallback)
                    processed_content = await _process_skill_invocations(
                        state["latest_assistant_message"], active_skills, db, user.id
                    )
                    # Persist
                    messages.append({"role": "assistant", "content": processed_content})
                    session.raw_messages = _json.dumps(messages, ensure_ascii=False)
                    session.status = state["status"]
                    if state.get("summary_json"):
                        session.extracted_fields = _json.dumps(state["summary_json"], ensure_ascii=False)
                        session.triage_level = state["summary_json"].get("triage_level", "observe")
                        session.summary = state["summary_json"].get("summary_text", "")
                    await db.flush()
                    await db.commit()

                    # Flush Langfuse traces
                    flush_langfuse()

                    done_data = _json.dumps({
                        "assistant_message": processed_content,
                        "status": state["status"],
                        "red_flag_detected": state["red_flag_detected"],
                        "structured_state": state.get("extracted_fields") or {},
                        "current_agent": state.get("current_agent", ""),
                    }, ensure_ascii=False)
                    yield f"event: done\ndata: {done_data}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {_json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(_sse_generator(), media_type="text/event-stream")


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
