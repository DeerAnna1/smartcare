"""Proactive intervention APIs."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user_required
from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import (
    HealthEvent,
    ProactiveInterventionLog,
    ProactiveRule,
    User,
)
from app.schemas.schemas import CreateProactiveRuleRequest, ProactiveRuleResponse
from app.services.event_trigger_engine import build_intervention_message
from app.services.weather_provider import fetch_weather_alert

router = APIRouter(prefix="/proactive", tags=["proactive"])
settings = get_settings()


@router.post("/rules", response_model=ProactiveRuleResponse, status_code=201)
async def create_rule(
    body: CreateProactiveRuleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    rule = ProactiveRule(
        user_id=user.id,
        condition_type=body.condition_type,
        condition_value=body.condition_value,
        city=body.city,
        enabled=body.enabled,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return ProactiveRuleResponse(
        id=rule.id,
        condition_type=rule.condition_type,
        condition_value=rule.condition_value,
        city=rule.city,
        enabled=rule.enabled,
        created_at=rule.created_at,
    )


@router.get("/rules", response_model=list[ProactiveRuleResponse])
async def list_rules(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(ProactiveRule)
        .where(ProactiveRule.user_id == user.id)
        .order_by(ProactiveRule.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        ProactiveRuleResponse(
            id=row.id,
            condition_type=row.condition_type,
            condition_value=row.condition_value,
            city=row.city,
            enabled=row.enabled,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/run")
async def run_proactive_scan(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(ProactiveRule).where(ProactiveRule.user_id == user.id, ProactiveRule.enabled.is_(True))
    )
    rules = result.scalars().all()
    triggered: list[dict] = []
    for rule in rules:
        weather = await fetch_weather_alert(settings.WEATHER_API_BASE, rule.city or settings.DEFAULT_USER_CITY)
        if not weather.get("cold_wave"):
            continue
        message = build_intervention_message(rule.condition_value, weather)
        log = ProactiveInterventionLog(
            user_id=user.id,
            rule_id=rule.id,
            trigger_type="weather-cold-wave",
            payload=json.dumps(weather, ensure_ascii=False),
            message=message,
        )
        db.add(log)
        event = HealthEvent(
            user_id=user.id,
            source_session_id="proactive-engine",
            status="CREATED",
            chief_complaint="主动健康干预提醒",
            symptom_summary=json.dumps([message], ensure_ascii=False),
            red_flags=json.dumps([], ensure_ascii=False),
            candidate_conditions=json.dumps([], ensure_ascii=False),
            visit_preparation=json.dumps([], ensure_ascii=False),
            care_todos=json.dumps([message], ensure_ascii=False),
            medication_reminder_suggestion=json.dumps([], ensure_ascii=False),
            followup_reminder_suggestion=json.dumps([], ensure_ascii=False),
            insurance_material_suggestion=json.dumps([], ensure_ascii=False),
            triage_level="observe",
            recommended_department="全科",
        )
        db.add(event)
        triggered.append({"rule_id": rule.id, "message": message, "weather": weather})
    await db.flush()
    return {"success": True, "triggered_count": len(triggered), "triggered": triggered}
