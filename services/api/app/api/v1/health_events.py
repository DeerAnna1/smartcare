"""通用执行工作区 API — 健康事件、推荐任务"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, update
from app.api.deps.auth import get_current_user_required
from app.core.database import get_db
from app.models.models import (
    HealthEvent, HealthRecord, RegistrationOrder, ReminderTask, User,
)
from app.schemas.schemas import (
    EventCardResponse, ConfirmEventCardRequest,
    RecommendationsResponse, TaskRecommendation,
)

router = APIRouter(prefix="/health-events", tags=["健康事件"])


@router.get("", response_model=list[EventCardResponse])
async def list_events(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(HealthEvent)
        .where(HealthEvent.user_id == user.id)
        .order_by(HealthEvent.created_at.desc())
    )
    events = result.scalars().all()
    archived_records = await db.execute(
        select(HealthRecord.event_id)
        .where(HealthRecord.user_id == user.id)
        .where(HealthRecord.event_id.is_not(None))
    )
    archived_event_ids = {event_id for event_id in archived_records.scalars().all() if event_id}
    return [
        EventCardResponse(
            event_id=e.id,
            status=e.status,
            chief_complaint=e.chief_complaint,
            triage_level=e.triage_level,
            recommended_department=e.recommended_department,
            created_at=e.created_at,
            archived=e.id in archived_event_ids,
        )
        for e in events
    ]


@router.get("/{event_id}", response_model=dict)
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(HealthEvent).where(HealthEvent.id == event_id, HealthEvent.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="事件卡不存在")

    archived_result = await db.execute(
        select(HealthRecord.id).where(
            HealthRecord.event_id == event.id,
            HealthRecord.user_id == user.id,
        ).limit(1)
    )

    return {
        "event_id": event.id,
        "status": event.status,
        "chief_complaint": event.chief_complaint,
        "symptom_summary": json.loads(event.symptom_summary),
        "duration": event.duration,
        "severity": event.severity,
        "confirmed_points": json.loads(event.confirmed_points),
        "uncertain_points": json.loads(event.uncertain_points),
        "red_flags": json.loads(event.red_flags),
        "candidate_conditions": json.loads(event.candidate_conditions),
        "triage_level": event.triage_level,
        "recommended_department": event.recommended_department,
        "visit_preparation": json.loads(event.visit_preparation),
        "care_todos": json.loads(event.care_todos),
        "medication_reminder_suggestion": json.loads(event.medication_reminder_suggestion),
        "followup_reminder_suggestion": json.loads(event.followup_reminder_suggestion),
        "record_update_suggestion": event.record_update_suggestion,
        "insurance_material_suggestion": json.loads(event.insurance_material_suggestion),
        "source_session_id": event.source_session_id,
        "created_at": event.created_at.isoformat(),
        "archived": archived_result.scalar_one_or_none() is not None,
    }


@router.post("/{event_id}/confirm")
async def confirm_event(
    event_id: str,
    body: ConfirmEventCardRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(HealthEvent).where(HealthEvent.id == event_id, HealthEvent.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="事件卡不存在")

    event.status = "CONFIRMED"
    await db.flush()
    return {"success": True, "event_id": event_id, "status": "CONFIRMED"}


@router.post("/{event_id}/execute")
async def execute_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """执行事件卡中的所有推荐任务"""
    result = await db.execute(
        select(HealthEvent).where(HealthEvent.id == event_id, HealthEvent.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="事件卡不存在")

    # 将当前事件的所有任务统一置为完成，保证执行进度可达 100%
    completion_status = json.loads(event.task_completion_status or "{}")
    task_ids: list[str] = [
        f"task-med-{event_id[:8]}",
        f"task-followup-{event_id[:8]}",
    ]
    if event.record_update_suggestion:
        task_ids.append(f"task-record-{event_id[:8]}")
    care_items: list[str] = json.loads(event.care_todos or "[]")
    if care_items:
        task_ids.append(f"task-care-{event_id[:8]}")
    for task_id in task_ids:
        completion_status[task_id] = "completed"
    event.task_completion_status = json.dumps(completion_status, ensure_ascii=False)

    # 标记事件状态为 EXECUTED
    event.status = "EXECUTED"

    # 自动创建归档记录（幂等：同 event_id 只创建一次）
    existing_record = await db.execute(
        select(HealthRecord).where(HealthRecord.event_id == event.id)
    )
    if existing_record.scalar_one_or_none() is None:
        record = HealthRecord(
            user_id=event.user_id,
            event_id=event.id,
            created_at=event.created_at,
            title=event.chief_complaint or "健康问诊归档",
            department=event.recommended_department or "全科",
            tags=json.dumps(["会话归档", "待同步EHR"], ensure_ascii=False),
            structured_data=json.dumps(
                {
                    "event_id": event.id,
                    "triage_level": event.triage_level,
                    "candidate_conditions": json.loads(event.candidate_conditions or "[]"),
                    "summary": {
                        "chief_complaint": event.chief_complaint,
                        "symptom_summary": json.loads(event.symptom_summary or "[]"),
                    },
                },
                ensure_ascii=False,
            ),
            sync_status="pending",
        )
        db.add(record)

    await db.flush()
    await db.commit()
    
    return {
        "success": True,
        "event_id": event_id,
        "status": "EXECUTED",
        "message": "所有推荐任务已执行"
    }


@router.post("/{event_id}/archive")
async def archive_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(HealthEvent).where(HealthEvent.id == event_id, HealthEvent.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="事件卡不存在")

    existing_record = await db.execute(
        select(HealthRecord).where(HealthRecord.event_id == event.id)
    )
    record = existing_record.scalar_one_or_none()

    if record is None:
        record = HealthRecord(
            user_id=event.user_id,
            event_id=event.id,
            created_at=event.created_at,
            title=event.chief_complaint or "健康问诊归档",
            department=event.recommended_department or "全科",
            tags=json.dumps(["会话归档", "待同步EHR"], ensure_ascii=False),
            structured_data=json.dumps(
                {
                    "event_id": event.id,
                    "triage_level": event.triage_level,
                    "candidate_conditions": json.loads(event.candidate_conditions or "[]"),
                    "summary": {
                        "chief_complaint": event.chief_complaint,
                        "symptom_summary": json.loads(event.symptom_summary or "[]"),
                    },
                },
                ensure_ascii=False,
            ),
            sync_status="pending",
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)

    return {
        "success": True,
        "event_id": event.id,
        "record_id": record.id,
        "message": "事件已归档到健康档案",
    }


@router.delete("/{event_id}/archive")
async def unarchive_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """取消归档，并移除该事件已同步到 EHR 的关联健康档案。"""
    result = await db.execute(
        select(HealthEvent).where(HealthEvent.id == event_id, HealthEvent.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="事件卡不存在")

    records = await db.execute(
        select(HealthRecord).where(
            HealthRecord.event_id == event.id,
            HealthRecord.user_id == user.id,
        )
    )
    linked_records = records.scalars().all()
    synced_deleted = sum(record.sync_status == "synced" for record in linked_records)
    for record in linked_records:
        await db.delete(record)
    await db.flush()
    return {
        "success": True,
        "event_id": event.id,
        "deleted_record_count": len(linked_records),
        "deleted_ehr_count": synced_deleted,
        "archived": False,
    }


@router.delete("/{event_id}")
async def delete_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """删除通用执行及其提醒、健康档案和 EHR 同步数据。"""
    result = await db.execute(
        select(HealthEvent).where(HealthEvent.id == event_id, HealthEvent.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="事件卡不存在")

    records = await db.execute(
        select(HealthRecord).where(
            HealthRecord.event_id == event.id,
            HealthRecord.user_id == user.id,
        )
    )
    linked_records = records.scalars().all()
    synced_deleted = sum(record.sync_status == "synced" for record in linked_records)

    # Keep real appointment orders, but detach them from the deleted execution.
    await db.execute(
        update(RegistrationOrder)
        .where(RegistrationOrder.health_event_id == event.id)
        .values(health_event_id=None)
    )
    await db.execute(delete(ReminderTask).where(ReminderTask.event_id == event.id))
    await db.execute(delete(HealthRecord).where(HealthRecord.event_id == event.id))
    await db.delete(event)
    await db.flush()
    return {
        "success": True,
        "event_id": event_id,
        "deleted_record_count": len(linked_records),
        "deleted_ehr_count": synced_deleted,
    }


@router.post("/{event_id}/tasks/{task_id}/complete")
async def complete_task(
    event_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """标记任务为完成"""
    result = await db.execute(
        select(HealthEvent).where(HealthEvent.id == event_id, HealthEvent.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="事件卡不存在")

    # 更新任务完成状态
    completion_status = json.loads(event.task_completion_status or "{}")
    completion_status[task_id] = "completed"
    event.task_completion_status = json.dumps(completion_status, ensure_ascii=False)
    await db.flush()
    await db.commit()

    return {
        "success": True,
        "event_id": event_id,
        "task_id": task_id,
        "status": "completed"
    }


@router.get("/{event_id}/tasks", response_model=RecommendationsResponse)
async def get_recommended_tasks(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(HealthEvent).where(HealthEvent.id == event_id, HealthEvent.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="事件卡不存在")

    # 读取任务完成状态
    completion_status = json.loads(event.task_completion_status or "{}")

    tasks: list[TaskRecommendation] = []

    med_id = f"task-med-{event_id[:8]}"
    med_suggestions: list[str] = json.loads(event.medication_reminder_suggestion)
    tasks.append(TaskRecommendation(
        id=med_id,
        type="medication",
        title="用药提醒",
        description="；".join(med_suggestions) if med_suggestions else "根据问诊建议设置用药提醒",
        priority="high",
        status="completed" if completion_status.get(med_id) == "completed" else "pending",
    ))

    followup_id = f"task-followup-{event_id[:8]}"
    followup: list[str] = json.loads(event.followup_reminder_suggestion)
    tasks.append(TaskRecommendation(
        id=followup_id,
        type="followup",
        title="复诊提醒",
        description="；".join(followup) if followup else f"建议到{event.recommended_department or '相关科室'}复诊",
        priority="medium",
        status="completed" if completion_status.get(followup_id) == "completed" else "pending",
    ))

    if event.record_update_suggestion:
        record_id = f"task-record-{event_id[:8]}"
        tasks.append(TaskRecommendation(
            id=record_id,
            type="record",
            title="健康档案更新",
            description=f"将本次问诊（{event.chief_complaint}）录入档案",
            priority="medium",
            status="completed" if completion_status.get(record_id) == "completed" else "pending",
        ))

    care: list[str] = json.loads(event.care_todos)
    if care:
        care_id = f"task-care-{event_id[:8]}"
        tasks.append(TaskRecommendation(
            id=care_id,
            type="care",
            title="护理待办",
            description="；".join(care),
            priority="low",
            status="completed" if completion_status.get(care_id) == "completed" else "pending",
        ))

    return RecommendationsResponse(event_id=event_id, tasks=tasks)
