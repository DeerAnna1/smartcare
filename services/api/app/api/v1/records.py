"""健康档案 API"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from app.api.deps.auth import get_current_user_required
from app.core.database import get_db
from app.models.models import HealthEvent, HealthRecord, User
from app.schemas.schemas import (
    CreateRecordRequest,
    ExportEhrPdfRequest,
    HealthArchiveProfileRequest,
    HealthArchiveProfileResponse,
    RecordResponse,
    GenerateEhrSummaryRequest,
    GenerateEhrSummaryResponse,
)
from app.core.llm import get_llm_client
from app.core.config import get_settings

router = APIRouter(prefix="/records", tags=["健康档案"])
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def _safe_json_loads(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _safe_parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _set_ehr_tag(record: HealthRecord, synced: bool) -> None:
    try:
        tags = json.loads(record.tags or "[]")
    except json.JSONDecodeError:
        tags = []
    tags = [tag for tag in tags if tag not in ("待同步EHR", "已同步EHR")]
    tags.append("已同步EHR" if synced else "待同步EHR")
    record.tags = json.dumps(tags, ensure_ascii=False)


@router.get("/profile", response_model=HealthArchiveProfileResponse)
async def get_health_archive_profile(
    user: User = Depends(get_current_user_required),
):
    profile = _safe_json_loads(user.profile)
    preferences = _safe_json_loads(user.preferences)
    archive_profile = preferences.get("health_archive_profile") or {}

    updated_at = _safe_parse_dt(archive_profile.get("last_saved_at")) or user.created_at

    return HealthArchiveProfileResponse(
        name=archive_profile.get("name") or profile.get("name") or "",
        gender=archive_profile.get("gender") or "",
        age=archive_profile.get("age") or "",
        contact=archive_profile.get("contact") or "",
        manual_history=archive_profile.get("manual_history") or "",
        updated_at=updated_at,
    )


@router.put("/profile", response_model=HealthArchiveProfileResponse)
async def update_health_archive_profile(
    body: HealthArchiveProfileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    profile = _safe_json_loads(user.profile)
    preferences = _safe_json_loads(user.preferences)
    now_ts = datetime.now(timezone.utc)

    profile["name"] = body.name.strip()
    preferences["health_archive_profile"] = {
        "name": body.name.strip(),
        "gender": body.gender.strip(),
        "age": body.age.strip(),
        "contact": body.contact.strip(),
        "manual_history": body.manual_history.strip(),
        "last_saved_at": now_ts.isoformat(),
    }

    user.profile = json.dumps(profile, ensure_ascii=False)
    user.preferences = json.dumps(preferences, ensure_ascii=False)
    await db.flush()
    await db.refresh(user)

    return HealthArchiveProfileResponse(
        name=preferences["health_archive_profile"]["name"],
        gender=preferences["health_archive_profile"]["gender"],
        age=preferences["health_archive_profile"]["age"],
        contact=preferences["health_archive_profile"]["contact"],
        manual_history=preferences["health_archive_profile"]["manual_history"],
        updated_at=now_ts,
    )


@router.get("", response_model=list[RecordResponse])
async def list_records(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(HealthRecord, HealthEvent.created_at.label("event_created_at"))
        .outerjoin(HealthEvent, HealthEvent.id == HealthRecord.event_id)
        .where(HealthRecord.user_id == user.id)
        .order_by(HealthRecord.created_at.desc())
    )
    rows = result.all()
    return [
        RecordResponse(
            id=record.id,
            title=record.title,
            department=record.department,
            sync_status=record.sync_status,
            tags=json.loads(record.tags),
            event_id=record.event_id,
            # Event-linked archives display the original execution time.
            # Standalone health records retain their own creation time.
            created_at=event_created_at or record.created_at,
        )
        for record, event_created_at in rows
    ]


@router.post("", response_model=RecordResponse, status_code=201)
async def create_record(
    body: CreateRecordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    record = HealthRecord(
        user_id=user.id,
        title=body.title,
        department=body.department,
        event_id=body.event_id,
        tags=json.dumps(body.tags, ensure_ascii=False),
        structured_data=json.dumps(body.structured_data, ensure_ascii=False),
        sync_status="pending",
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return RecordResponse(
        id=record.id,
        title=record.title,
        department=record.department,
        sync_status=record.sync_status,
        tags=json.loads(record.tags),
        event_id=record.event_id,
        created_at=record.created_at,
    )


@router.post("/{record_id}/sync")
async def sync_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(HealthRecord).where(HealthRecord.id == record_id, HealthRecord.user_id == user.id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="档案不存在")

    record.sync_status = "synced"
    _set_ehr_tag(record, synced=True)
    await db.flush()
    return {"success": True, "record_id": record.id, "sync_status": record.sync_status}


@router.delete("/{record_id}/sync")
async def unsync_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """取消同步，使该健康档案不再参与 EHR 汇总。"""
    result = await db.execute(
        select(HealthRecord).where(HealthRecord.id == record_id, HealthRecord.user_id == user.id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="档案不存在")

    record.sync_status = "pending"
    _set_ehr_tag(record, synced=False)
    await db.flush()
    return {"success": True, "record_id": record.id, "sync_status": record.sync_status}


@router.post("/sync")
async def batch_sync_records(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(HealthRecord)
        .where(HealthRecord.user_id == user.id)
        .where(HealthRecord.sync_status != "synced")
    )
    records = result.scalars().all()

    for record in records:
        record.sync_status = "synced"
        _set_ehr_tag(record, synced=True)

    await db.flush()
    return {
        "success": True,
        "synced_count": len(records),
    }


@router.post("/ehr-summary", response_model=GenerateEhrSummaryResponse)
async def generate_ehr_summary(
    body: GenerateEhrSummaryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(HealthRecord)
        .where(HealthRecord.user_id == user.id)
        .where(HealthRecord.sync_status == "synced")
        .order_by(HealthRecord.created_at.desc())
    )
    records = result.scalars().all()

    archived_context = []
    for index, record in enumerate(records, start=1):
        structured_data = json.loads(record.structured_data or "{}")
        archived_context.append({
            "index": index,
            "title": record.title,
            "department": record.department,
            "sync_status": record.sync_status,
            "tags": json.loads(record.tags or "[]"),
            "structured_data": structured_data,
            "created_at": record.created_at.isoformat(),
        })

    manual_history = (body.manual_history or "").strip()
    archived_json = json.dumps(archived_context, ensure_ascii=False, indent=2)

    if not manual_history and not archived_context:
        return GenerateEhrSummaryResponse(summary="暂无可生成的 EHR 内容。", archived_record_count=0)

    settings = get_settings()
    client = get_llm_client()
    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是医疗档案整理助手。请根据用户提供的既往病史和历史归档内容，输出一份结构化、简洁、适合个人长期保存的完整 EHR 摘要。"
                    "内容请使用中文，包含以下部分：基本情况、既往病史、重要症状/事件、分诊/科室建议、当前需要关注事项。"
                    "如果信息不足，不要编造，用'未提供'表示。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用户手动输入的既往病史信息：\n{manual_history or '未提供'}\n\n"
                    f"系统内已有归档健康记录：\n{archived_json}"
                ),
            },
        ],
    )

    summary = response.choices[0].message.content or "生成 EHR 失败，请重试。"
    return GenerateEhrSummaryResponse(
        summary=summary,
        archived_record_count=len(archived_context),
    )


@router.post("/export-pdf")
async def export_ehr_pdf(
    body: ExportEhrPdfRequest,
    user: User = Depends(get_current_user_required),
):
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="导出内容不能为空")

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    pdf.setFont("STSong-Light", 11)
    left = 40
    top = height - 48
    line_height = 18
    y = top

    for raw_line in body.content.splitlines() or [""]:
        line = raw_line.rstrip() or " "
        # 粗略按中文排版宽度拆行，避免内容溢出页面
        chunks = [line[i:i + 48] for i in range(0, len(line), 48)] or [" "]
        for chunk in chunks:
            if y < 42:
                pdf.showPage()
                pdf.setFont("STSong-Light", 11)
                y = top
            pdf.drawString(left, y, chunk)
            y -= line_height

    pdf.save()
    buffer.seek(0)

    safe_filename = (body.filename or "complete-ehr.pdf").replace("\n", "").replace('"', "")
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_filename}"'
    }
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)
