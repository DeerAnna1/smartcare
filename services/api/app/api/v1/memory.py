"""M4: 长期记忆 API — 管理用户健康记忆事实。"""
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user_required
from app.core.database import get_db
from app.models.models import User, MemoryFact

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/memory", tags=["长期记忆"])


@router.get("/facts")
async def list_memory_facts(
    fact_type: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """列出用户的记忆事实。"""
    query = select(MemoryFact).where(MemoryFact.user_id == user.id)
    if fact_type:
        query = query.where(MemoryFact.fact_type == fact_type)
    if status:
        query = query.where(MemoryFact.status == status)
    query = query.order_by(MemoryFact.created_at.desc()).limit(limit)

    result = await db.execute(query)
    facts = result.scalars().all()
    return [
        {
            "id": f.id,
            "fact_type": f.fact_type,
            "value": json.loads(f.value_json),
            "source_type": f.source_type,
            "source_id": f.source_id,
            "confidence": f.confidence,
            "status": f.status,
            "valid_from": f.valid_from.isoformat() if f.valid_from else None,
            "valid_to": f.valid_to.isoformat() if f.valid_to else None,
            "supersedes_fact_id": f.supersedes_fact_id,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in facts
    ]


@router.post("/facts")
async def create_memory_fact(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """创建新的记忆事实（默认 proposed 状态）。"""
    fact = MemoryFact(
        user_id=user.id,
        fact_type=body.get("fact_type", "other"),
        value_json=json.dumps(body.get("value", {}), ensure_ascii=False),
        source_type=body.get("source_type", "user_message"),
        source_id=body.get("source_id", ""),
        confidence=body.get("confidence", 0.5),
        status="proposed",
    )
    db.add(fact)
    await db.flush()
    await db.refresh(fact)
    return {
        "id": fact.id,
        "fact_type": fact.fact_type,
        "status": fact.status,
        "created_at": fact.created_at.isoformat() if fact.created_at else None,
    }


@router.put("/facts/{fact_id}/confirm")
async def confirm_memory_fact(
    fact_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """确认一条 proposed 事实。"""
    result = await db.execute(
        select(MemoryFact).where(
            MemoryFact.id == fact_id,
            MemoryFact.user_id == user.id,
        )
    )
    fact = result.scalar_one_or_none()
    if not fact:
        raise HTTPException(status_code=404, detail="记忆事实不存在")
    if fact.status != "proposed":
        raise HTTPException(status_code=400, detail=f"只能确认 proposed 状态的事实，当前状态: {fact.status}")

    fact.status = "confirmed"
    await db.flush()
    return {"id": fact.id, "status": "confirmed"}


@router.put("/facts/{fact_id}/reject")
async def reject_memory_fact(
    fact_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """拒绝一条 proposed 事实。"""
    result = await db.execute(
        select(MemoryFact).where(
            MemoryFact.id == fact_id,
            MemoryFact.user_id == user.id,
        )
    )
    fact = result.scalar_one_or_none()
    if not fact:
        raise HTTPException(status_code=404, detail="记忆事实不存在")

    fact.status = "rejected"
    await db.flush()
    return {"id": fact.id, "status": "rejected"}


@router.delete("/facts/{fact_id}")
async def delete_memory_fact(
    fact_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """删除一条记忆事实。"""
    result = await db.execute(
        select(MemoryFact).where(
            MemoryFact.id == fact_id,
            MemoryFact.user_id == user.id,
        )
    )
    fact = result.scalar_one_or_none()
    if not fact:
        raise HTTPException(status_code=404, detail="记忆事实不存在")

    await db.delete(fact)
    await db.flush()
    return {"status": "deleted", "id": fact_id}


async def get_confirmed_facts(
    db: AsyncSession,
    user_id: str,
    fact_types: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    """获取已确认的记忆事实（供 ContextBuilder 使用）。"""
    query = select(MemoryFact).where(
        MemoryFact.user_id == user_id,
        MemoryFact.status == "confirmed",
    )
    if fact_types:
        query = query.where(MemoryFact.fact_type.in_(fact_types))
    query = query.order_by(MemoryFact.confidence.desc()).limit(limit)

    result = await db.execute(query)
    facts = result.scalars().all()
    return [
        {
            "id": f.id,
            "fact_type": f.fact_type,
            "value": json.loads(f.value_json),
            "confidence": f.confidence,
            "source_type": f.source_type,
        }
        for f in facts
    ]


@router.post("/facts/direct")
async def create_direct_memory(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """用户直接创建长期记忆（自动确认）。"""
    from app.models.models import MemoryFact
    import json

    text = (body.get("text") or "").strip()
    fact_type = (body.get("fact_type") or "preference").strip()
    if not text:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")

    fact = MemoryFact(
        user_id=user.id,
        fact_type=fact_type,
        value_json=json.dumps({"text": text}, ensure_ascii=False),
        source_type="user_direct",
        confidence=1.0,
        status="confirmed",
    )
    db.add(fact)
    await db.commit()
    await db.refresh(fact)
    return {"id": fact.id, "status": "confirmed", "fact_type": fact_type, "text": text}
