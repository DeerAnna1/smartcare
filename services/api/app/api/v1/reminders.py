"""提醒任务 API"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.models import ReminderTask
from app.schemas.schemas import CreateReminderRequest, ReminderResponse

router = APIRouter(prefix="/reminders", tags=["提醒任务"])


@router.get("", response_model=list[ReminderResponse])
async def list_reminders(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ReminderTask).order_by(ReminderTask.created_at.desc()))
    reminders = result.scalars().all()
    return [
        ReminderResponse(
            id=r.id,
            task_type=r.task_type,
            title=r.title,
            description=r.description,
            schedule=json.loads(r.schedule),
            repeat_rule=r.repeat_rule,
            status=r.status,
            event_id=r.event_id,
            created_at=r.created_at,
        )
        for r in reminders
    ]


@router.post("", response_model=ReminderResponse, status_code=201)
async def create_reminder(
    body: CreateReminderRequest,
    db: AsyncSession = Depends(get_db),
):
    reminder = ReminderTask(
        task_type=body.task_type,
        title=body.title,
        description=body.description,
        schedule=json.dumps(body.schedule, ensure_ascii=False),
        repeat_rule=body.repeat_rule,
        event_id=body.event_id,
        status="active",
    )
    db.add(reminder)
    await db.flush()
    await db.refresh(reminder)
    return ReminderResponse(
        id=reminder.id,
        task_type=reminder.task_type,
        title=reminder.title,
        description=reminder.description,
        schedule=json.loads(reminder.schedule),
        repeat_rule=reminder.repeat_rule,
        status=reminder.status,
        event_id=reminder.event_id,
        created_at=reminder.created_at,
    )


@router.patch("/{reminder_id}/status")
async def update_reminder_status(
    reminder_id: str,
    status: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ReminderTask).where(ReminderTask.id == reminder_id))
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="提醒不存在")
    reminder.status = status
    await db.flush()
    return {"success": True, "id": reminder_id, "status": status}
