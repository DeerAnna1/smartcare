"""Human handoff management."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user_required
from app.core.database import get_db
from app.models.models import HandoffTicket, User
from app.schemas.schemas import HandoffTicketResponse, UpdateHandoffStatusRequest

router = APIRouter(prefix="/handoffs", tags=["handoffs"])


@router.get("", response_model=list[HandoffTicketResponse])
async def list_handoffs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(HandoffTicket)
        .where(HandoffTicket.user_id == user.id)
        .order_by(HandoffTicket.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        HandoffTicketResponse(
            id=row.id,
            session_id=row.session_id,
            status=row.status,
            risk_level=row.risk_level,
            reason=row.reason,
            brief=row.brief,
            evidence=json.loads(row.evidence or "[]"),
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.patch("/{ticket_id}", response_model=HandoffTicketResponse)
async def update_handoff_status(
    ticket_id: str,
    body: UpdateHandoffStatusRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(HandoffTicket).where(HandoffTicket.id == ticket_id, HandoffTicket.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="接管工单不存在")
    row.status = body.status
    await db.flush()
    await db.refresh(row)
    return HandoffTicketResponse(
        id=row.id,
        session_id=row.session_id,
        status=row.status,
        risk_level=row.risk_level,
        reason=row.reason,
        brief=row.brief,
        evidence=json.loads(row.evidence or "[]"),
        created_at=row.created_at,
    )
