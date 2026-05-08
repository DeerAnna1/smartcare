"""挂号服务 API — 7 个工具端点"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user_required
from app.core.database import get_db
from app.models.models import User
from app.services.registration import RegistrationService

router = APIRouter(prefix="/registration", tags=["挂号服务"])


# ─── 请求体 ────────────────────────────────────────────────────────────────────

class LockSlotRequest(BaseModel):
    schedule_id: str
    patient_name: str = Field(..., min_length=1)
    patient_id_last4: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
    health_event_id: str | None = None


class ConfirmRequest(BaseModel):
    order_id: str


class CancelRequest(BaseModel):
    order_id: str
    reason: str = ""


# ─── 1. 查询医院 ───────────────────────────────────────────────────────────────

@router.get("/hospitals")
async def search_hospital(
    city: str = "",
    keyword: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """搜索医院列表，支持城市和关键词过滤"""
    svc = RegistrationService(db)
    return await svc.search_hospital(city=city, keyword=keyword)


# ─── 2. 查询科室 ───────────────────────────────────────────────────────────────

@router.get("/departments")
async def search_department(
    hospital_id: str,
    keyword: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """查询医院下的科室列表"""
    svc = RegistrationService(db)
    return await svc.search_department(hospital_id=hospital_id, keyword=keyword)


# ─── 3. 查询医生排班 ────────────────────────────────────────────────────────────

@router.get("/schedules")
async def search_doctor_schedule(
    department_id: str,
    date: str,  # YYYY-MM-DD
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """查询指定科室指定日期的医生排班和号源"""
    svc = RegistrationService(db)
    return await svc.search_doctor_schedule(department_id=department_id, date=date)


# ─── 4. 便捷排班查询（供 Skill Runtime 直接调用）──────────────────────────────────

@router.get("/schedules/quick")
async def quick_schedule_search(
    hospital: str = "",
    department: str = "",
    date: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """按医院名+科室名+日期一步查询排班（不需要预先知道 ID）"""
    svc = RegistrationService(db)
    return await svc.search_by_department_name(
        hospital_name=hospital, department_name=department, date=date
    )


# ─── 5. 锁号 ──────────────────────────────────────────────────────────────────

@router.post("/lock")
async def lock_slot(
    body: LockSlotRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """锁定号源，创建 LOCKED 状态订单，有效期 15 分钟"""
    svc = RegistrationService(db)
    result = await svc.lock_slot(
        user_id=user.id,
        schedule_id=body.schedule_id,
        patient_name=body.patient_name,
        patient_id_last4=body.patient_id_last4,
        health_event_id=body.health_event_id,
    )
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("error", "锁号失败"))
    return result


# ─── 6. 确认挂号 ───────────────────────────────────────────────────────────────

@router.post("/confirm")
async def confirm_registration(
    body: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """确认挂号，LOCKED → CONFIRMED"""
    svc = RegistrationService(db)
    result = await svc.confirm_registration(order_id=body.order_id, user_id=user.id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "确认失败"))
    return result


# ─── 7. 取消挂号 ───────────────────────────────────────────────────────────────

@router.post("/cancel")
async def cancel_registration(
    body: CancelRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """取消挂号，归还号源"""
    svc = RegistrationService(db)
    result = await svc.cancel_registration(
        order_id=body.order_id, user_id=user.id, reason=body.reason
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "取消失败"))
    return result


# ─── 8. 查询订单详情 ────────────────────────────────────────────────────────────

@router.get("/orders/{order_id}")
async def get_registration_record(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """查询挂号订单详情"""
    svc = RegistrationService(db)
    result = await svc.get_registration_record(order_id=order_id, user_id=user.id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "订单不存在"))
    return result
