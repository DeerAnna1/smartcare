"""IoT vitals webhook endpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user_required
from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import AuditLog, ConsultationSession, HandoffTicket, User, VitalStreamEvent
from app.schemas.schemas import IoTWebhookRequest

router = APIRouter(prefix="/iot", tags=["iot"])
settings = get_settings()


def _calc_dedupe_key(payload: IoTWebhookRequest, user_id: str, nonce: str = "") -> str:
    raw = (
        f"{user_id}|{payload.source}|{payload.metric}|{payload.value}|"
        f"{payload.measured_at}|{payload.event_id}|{nonce}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _calc_hmac_signature(raw_body: bytes, timestamp: str, nonce: str) -> str:
    base = f"{timestamp}.{nonce}.".encode("utf-8") + raw_body
    digest = hmac.new(
        settings.IOT_WEBHOOK_HMAC_SECRET.encode("utf-8"),
        base,
        hashlib.sha256,
    ).hexdigest()
    return digest


async def _ingest_single_event(
    payload: IoTWebhookRequest,
    user_id: str,
    db: AsyncSession,
    nonce: str = "",
):
    dedupe_key = _calc_dedupe_key(payload, user_id, nonce)
    existing = await db.execute(select(VitalStreamEvent).where(VitalStreamEvent.dedupe_key == dedupe_key))
    if existing.scalar_one_or_none() is not None:
        return {"success": True, "deduped": True}

    risk_level = "normal"
    if payload.metric == "heart_rate" and payload.value >= 120:
        risk_level = "high"
    elif payload.metric == "heart_rate" and payload.value >= 100:
        risk_level = "medium"

    event = VitalStreamEvent(
        user_id=user_id,
        source=payload.source,
        metric=payload.metric,
        value=payload.value,
        unit=payload.unit,
        measured_at=payload.measured_at,
        dedupe_key=dedupe_key,
        risk_level=risk_level,
    )
    db.add(event)
    await db.flush()
    handoff_result = await _trigger_handoff_from_iot(event, db)
    return {
        "success": True,
        "risk_level": risk_level,
        "event_id": event.id,
        "handoff_triggered": handoff_result["triggered"],
        "handoff_ticket_id": handoff_result.get("ticket_id", ""),
        "handoff_session_id": handoff_result.get("session_id", ""),
    }


async def _trigger_handoff_from_iot(event: VitalStreamEvent, db: AsyncSession) -> dict:
    if event.risk_level != "high":
        return {"triggered": False}

    # 选择用户最近一个未关闭会话进行自动接管
    session_result = await db.execute(
        select(ConsultationSession)
        .where(ConsultationSession.user_id == event.user_id)
        .where(ConsultationSession.status.not_in(["CLOSED", "EVENT_CARD_READY"]))
        .order_by(ConsultationSession.updated_at.desc())
    )
    session = session_result.scalars().first()
    if session is None:
        return {"triggered": False}

    existing_ticket_res = await db.execute(
        select(HandoffTicket)
        .where(HandoffTicket.session_id == session.id)
        .where(HandoffTicket.status.in_(["pending", "processing"]))
        .order_by(HandoffTicket.created_at.desc())
    )
    existing_ticket = existing_ticket_res.scalars().first()
    if existing_ticket is not None:
        return {"triggered": False, "ticket_id": existing_ticket.id, "session_id": session.id}

    evidence = [
        f"source={event.source}",
        f"metric={event.metric}",
        f"value={event.value}{event.unit}",
        f"measured_at={event.measured_at}",
        f"event_id={event.id}",
    ]
    ticket = HandoffTicket(
        user_id=event.user_id,
        session_id=session.id,
        status="pending",
        risk_level="high",
        reason="IoT 高风险生命体征自动触发人工接管",
        brief=f"检测到 {event.metric}={event.value}{event.unit}（{event.risk_level}）",
        evidence=json.dumps(evidence, ensure_ascii=False),
    )
    db.add(ticket)
    session.status = "HUMAN_HANDOFF_PENDING"

    try:
        raw_messages = json.loads(session.raw_messages or "[]")
    except json.JSONDecodeError:
        raw_messages = []
    raw_messages.append(
        {
            "role": "assistant",
            "content": (
                "检测到穿戴设备高风险生命体征（已自动触发人工接管）。"
                "请立即停止剧烈活动，并尽快就医或联系急救。"
            ),
        }
    )
    session.raw_messages = json.dumps(raw_messages, ensure_ascii=False)

    db.add(
        AuditLog(
            event_type="handoff.created.iot",
            actor_id=event.user_id,
            entity_type="handoff_ticket",
            entity_id=ticket.id,
            detail=json.dumps({"session_id": session.id, "iot_event_id": event.id}, ensure_ascii=False),
        )
    )
    await db.flush()
    return {"triggered": True, "ticket_id": ticket.id, "session_id": session.id}


@router.post("/webhook")
async def ingest_vitals_webhook(
    request: Request,
    body: IoTWebhookRequest,
    x_webhook_signature: str = Header(default=""),
    x_iot_signature: str = Header(default=""),
    x_iot_timestamp: str = Header(default=""),
    x_iot_nonce: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
):
    # 兼容旧协议（共享密钥），优先新协议（HMAC）
    if x_iot_signature and x_iot_timestamp and x_iot_nonce:
        try:
            ts = int(x_iot_timestamp)
        except ValueError:
            raise HTTPException(status_code=400, detail="x-iot-timestamp 格式错误")
        now_ts = int(time.time())
        if abs(now_ts - ts) > settings.IOT_WEBHOOK_MAX_SKEW_SECONDS:
            raise HTTPException(status_code=401, detail="Webhook 请求已过期")
        raw = await request.body()
        expected = _calc_hmac_signature(raw, x_iot_timestamp, x_iot_nonce)
        if not hmac.compare_digest(expected, x_iot_signature):
            raise HTTPException(status_code=401, detail="Webhook HMAC 签名无效")
        nonce = x_iot_nonce
    elif x_webhook_signature == settings.WEBHOOK_SECRET:
        nonce = ""
    else:
        raise HTTPException(status_code=401, detail="Webhook signature 无效")

    user_id = body.user_id
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id 不能为空")
    return await _ingest_single_event(body, user_id, db, nonce)


@router.post("/simulate")
async def simulate_push(
    body: IoTWebhookRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """开发联调入口：用当前登录用户模拟一条设备推送。"""
    payload = body.model_copy(update={"user_id": user.id})
    nonce = f"sim-{int(time.time() * 1000)}"
    return await _ingest_single_event(payload, user.id, db, nonce=nonce)


@router.get("/latest")
async def get_latest_vitals(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(VitalStreamEvent)
        .where(VitalStreamEvent.user_id == user.id)
        .order_by(VitalStreamEvent.created_at.desc())
    )
    events = result.scalars().all()[:20]
    return [
        {
            "id": item.id,
            "source": item.source,
            "metric": item.metric,
            "value": item.value,
            "unit": item.unit,
            "measured_at": item.measured_at,
            "risk_level": item.risk_level,
            "created_at": item.created_at.isoformat(),
        }
        for item in events
    ]
