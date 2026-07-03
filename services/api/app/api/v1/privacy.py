"""隐私与数据生命周期 API：同意管理、数据导出、账户删除。"""
import json
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user_required
from app.core.database import get_db
from app.models.models import (
    User, ConsentRecord, DataExportJob, DeletionJob,
    ConsultationSession, ConversationMessage, HealthEvent,
    HealthRecord, ReminderTask, LabReport, VitalStreamEvent,
    HandoffTicket, AuditLog, ToolInvocationLog,
)
from app.schemas.schemas import (
    CreateConsentRequest, ConsentResponse,
    DataExportJobResponse, DeletionJobResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/privacy", tags=["隐私与数据"])


# ─── 同意管理 ──────────────────────────────────────────────────────────────

@router.post("/consent", response_model=ConsentResponse)
async def grant_consent(
    body: CreateConsentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """授予或更新用户同意。"""
    # 检查是否已有同类型的同意记录
    existing = await db.execute(
        select(ConsentRecord).where(
            ConsentRecord.user_id == user.id,
            ConsentRecord.consent_type == body.consent_type,
            ConsentRecord.revoked_at.is_(None),
        )
    )
    record = existing.scalar_one_or_none()

    if record:
        # 更新已有记录
        record.granted = body.granted
        record.policy_version = body.policy_version
        if not body.granted:
            record.revoked_at = datetime.now(timezone.utc)
    else:
        record = ConsentRecord(
            user_id=user.id,
            consent_type=body.consent_type,
            policy_version=body.policy_version,
            granted=body.granted,
        )
        if not body.granted:
            record.revoked_at = datetime.now(timezone.utc)
        db.add(record)

    await db.flush()
    await db.refresh(record)
    return ConsentResponse(
        id=record.id,
        consent_type=record.consent_type,
        policy_version=record.policy_version,
        granted=record.granted,
        granted_at=record.granted_at,
        revoked_at=record.revoked_at,
    )


@router.get("/consent", response_model=list[ConsentResponse])
async def list_consents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """列出当前用户的所有同意记录。"""
    result = await db.execute(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user.id)
        .order_by(ConsentRecord.created_at.desc())
    )
    records = result.scalars().all()
    return [
        ConsentResponse(
            id=r.id,
            consent_type=r.consent_type,
            policy_version=r.policy_version,
            granted=r.granted,
            granted_at=r.granted_at,
            revoked_at=r.revoked_at,
        )
        for r in records
    ]


@router.delete("/consent/{consent_type}")
async def revoke_consent(
    consent_type: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """撤回指定类型的同意。"""
    result = await db.execute(
        select(ConsentRecord).where(
            ConsentRecord.user_id == user.id,
            ConsentRecord.consent_type == consent_type,
            ConsentRecord.revoked_at.is_(None),
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="未找到有效的同意记录")

    record.granted = False
    record.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    return {"status": "revoked", "consent_type": consent_type}


# ─── 数据导出 ──────────────────────────────────────────────────────────────

@router.post("/export", response_model=DataExportJobResponse)
async def request_data_export(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """请求导出用户数据（会话、健康事件、记录、审计日志）。"""
    # 检查是否有进行中的导出任务
    existing = await db.execute(
        select(DataExportJob).where(
            DataExportJob.user_id == user.id,
            DataExportJob.status.in_(["pending", "processing"]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="已有进行中的导出任务")

    job = DataExportJob(user_id=user.id, status="pending")
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # 异步执行导出（后台任务）
    import asyncio
    asyncio.create_task(_execute_export(job.id, user.id))

    return DataExportJobResponse(
        id=job.id,
        status=job.status,
        created_at=job.created_at,
    )


async def _execute_export(job_id: str, user_id: str):
    """后台执行数据导出。"""
    from app.core.database import AsyncSessionLocal
    import tempfile
    import os

    try:
        async with AsyncSessionLocal() as db:
            job = await db.get(DataExportJob, job_id)
            if not job:
                return
            job.status = "processing"
            await db.flush()

            export_data = {}

            # 导出会话
            sessions = await db.execute(
                select(ConsultationSession).where(ConsultationSession.user_id == user_id)
            )
            export_data["sessions"] = [
                {
                    "id": s.id, "status": s.status,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "summary": s.summary,
                }
                for s in sessions.scalars().all()
            ]

            # 导出健康事件
            events = await db.execute(
                select(HealthEvent).where(HealthEvent.user_id == user_id)
            )
            export_data["health_events"] = [
                {
                    "id": e.id, "chief_complaint": e.chief_complaint,
                    "triage_level": e.triage_level,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events.scalars().all()
            ]

            # 导出健康记录
            records = await db.execute(
                select(HealthRecord).where(HealthRecord.user_id == user_id)
            )
            export_data["health_records"] = [
                {
                    "id": r.id, "title": r.title, "department": r.department,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records.scalars().all()
            ]

            # 导出审计日志
            audit = await db.execute(
                select(AuditLog).where(AuditLog.actor_id == user_id)
            )
            export_data["audit_logs"] = [
                {
                    "id": a.id, "event_type": a.event_type,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in audit.scalars().all()
            ]

            # 写入临时文件
            export_json = json.dumps(export_data, ensure_ascii=False, indent=2)
            tmp_dir = tempfile.mkdtemp()
            file_path = os.path.join(tmp_dir, f"export_{user_id[:8]}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(export_json)

            job.status = "completed"
            job.object_key = file_path
            job.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

    except Exception as e:
        logger.exception(f"数据导出失败: {e}")
        try:
            async with AsyncSessionLocal() as db:
                job = await db.get(DataExportJob, job_id)
                if job:
                    job.status = "failed"
                    job.error = str(e)[:500]
                    await db.commit()
        except Exception:
            pass


@router.get("/export", response_model=list[DataExportJobResponse])
async def list_export_jobs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """列出当前用户的数据导出任务。"""
    result = await db.execute(
        select(DataExportJob)
        .where(DataExportJob.user_id == user.id)
        .order_by(DataExportJob.created_at.desc())
    )
    jobs = result.scalars().all()
    return [
        DataExportJobResponse(
            id=j.id, status=j.status,
            created_at=j.created_at,
            expires_at=j.expires_at,
        )
        for j in jobs
    ]


# ─── 账户删除 ──────────────────────────────────────────────────────────────

@router.post("/delete-account", response_model=DeletionJobResponse)
async def request_account_deletion(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """请求删除用户账户及所有关联数据。"""
    # 检查是否有进行中的删除任务
    existing = await db.execute(
        select(DeletionJob).where(
            DeletionJob.user_id == user.id,
            DeletionJob.status.in_(["pending", "processing"]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="已有进行中的删除任务")

    job = DeletionJob(user_id=user.id, status="pending")
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # 异步执行删除
    import asyncio
    asyncio.create_task(_execute_deletion(job.id, user.id))

    return DeletionJobResponse(
        id=job.id, status=job.status, created_at=job.created_at,
    )


async def _execute_deletion(job_id: str, user_id: str):
    """后台执行账户删除：删除所有关联数据。"""
    from app.core.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            job = await db.get(DeletionJob, job_id)
            if not job:
                return
            job.status = "processing"
            job.started_at = datetime.now(timezone.utc)
            await db.flush()

            deleted_counts = {}

            # 按依赖顺序删除
            for model, label in [
                (ToolInvocationLog, "tool_invocation_logs"),
                (AuditLog, "audit_logs"),
                (VitalStreamEvent, "vital_stream_events"),
                (LabReport, "lab_reports"),
                (HandoffTicket, "handoff_tickets"),
                (ReminderTask, "reminder_tasks"),
                (HealthEvent, "health_events"),
                (HealthRecord, "health_records"),
                (ConversationMessage, "conversation_messages"),
                (ConsultationSession, "consultation_sessions"),
                (ConsentRecord, "consent_records"),
                (DataExportJob, "data_export_jobs"),
            ]:
                try:
                    # 多数模型有 user_id，AuditLog 用 actor_id
                    if model == AuditLog:
                        stmt = delete(model).where(model.actor_id == user_id)
                    elif model == ConversationMessage:
                        # 通过 session_id 关联
                        subq = select(ConsultationSession.id).where(
                            ConsultationSession.user_id == user_id
                        )
                        stmt = delete(model).where(model.session_id.in_(subq))
                    else:
                        stmt = delete(model).where(model.user_id == user_id)

                    result = await db.execute(stmt)
                    deleted_counts[label] = result.rowcount
                except Exception as e:
                    logger.warning(f"删除 {label} 失败: {e}")
                    deleted_counts[label] = f"error: {str(e)[:100]}"

            # 最后删除用户本身
            user = await db.get(User, user_id)
            if user:
                await db.delete(user)
                deleted_counts["user"] = 1

            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

            # 记录审计（在用户删除后仍保留不可还原的删除证明）
            logger.info(f"账户删除完成: user_id={user_id[:8]}..., deleted={deleted_counts}")

            # 清理 Redis 缓存
            try:
                from app.services.context_manager import _get_redis
                redis = await _get_redis()
                # 删除该用户的所有 session 缓存
                keys = await redis.keys(f"session:{user_id[:8]}*")
                if keys:
                    await redis.delete(*keys)
            except Exception:
                pass

    except Exception as e:
        logger.exception(f"账户删除失败: {e}")
        try:
            async with AsyncSessionLocal() as db:
                job = await db.get(DeletionJob, job_id)
                if job:
                    job.status = "failed"
                    job.error = str(e)[:500]
                    await db.commit()
        except Exception:
            pass