"""Background proactive intervention runner."""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.models import HealthEvent, ProactiveInterventionLog, ProactiveRule
from app.services.event_trigger_engine import build_intervention_message
from app.services.weather_provider import fetch_weather_alert

settings = get_settings()


async def run_once() -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ProactiveRule).where(ProactiveRule.enabled.is_(True)))
        rules = result.scalars().all()
        triggered = 0
        for rule in rules:
            weather = await fetch_weather_alert(settings.WEATHER_API_BASE, rule.city or settings.DEFAULT_USER_CITY)
            if not weather.get("cold_wave"):
                continue
            message = build_intervention_message(rule.condition_value, weather)
            db.add(
                ProactiveInterventionLog(
                    user_id=rule.user_id,
                    rule_id=rule.id,
                    trigger_type="weather-cold-wave",
                    payload=json.dumps(weather, ensure_ascii=False),
                    message=message,
                )
            )
            db.add(
                HealthEvent(
                    user_id=rule.user_id,
                    source_session_id="proactive-job",
                    status="CREATED",
                    chief_complaint="主动干预提醒",
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
            )
            triggered += 1
        await db.commit()
        return {"triggered": triggered}


if __name__ == "__main__":
    print(asyncio.run(run_once()))
