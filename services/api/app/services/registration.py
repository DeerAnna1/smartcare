"""
挂号服务层 — 适配器模式

架构：
  RegistrationService（业务逻辑）
    └─ HospitalAdapter（平台对接抽象）
         ├─ SeedAdapter       — 读本地 DB seed 数据（V1 当前）
         ├─ HisAdapter        — 对接医院 HIS 正式接口（V2 预留）
         └─ JiangtongAdapter  — 对接京通/区域统一预约平台（V2 预留）

调用链（V1）:
  search_hospital → 查 hospitals 表
  search_department → 查 departments 表（按 hospital_id）
  search_doctor_schedule → 查 doctor_schedules 表（按日期+科室）
  lock_slot → 创建 RegistrationOrder(LOCKED)，remaining_quota - 1
  confirm_registration → 订单 LOCKED → CONFIRMED
  cancel_registration → 订单 → CANCELLED，remaining_quota + 1
  get_registration_record → 查订单详情
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Protocol, Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Hospital, Department, DoctorSchedule, RegistrationOrder


# ─── 接口协议（V2 真实平台适配器遵循此协议）─────────────────────────────────────────

class IHospitalAdapter(Protocol):
    async def list_hospitals(self, city: str, keyword: str) -> list[dict]: ...
    async def list_departments(self, hospital_id: str, keyword: str) -> list[dict]: ...
    async def list_schedules(self, department_id: str, date: str) -> list[dict]: ...
    async def lock_slot(self, slot_id: str, patient_info: dict) -> dict: ...
    async def confirm_order(self, order_id: str) -> dict: ...
    async def cancel_order(self, order_id: str, reason: str) -> dict: ...


# ─── SeedAdapter：读本地 DB（V1）─────────────────────────────────────────────────

class SeedAdapter:
    """从本地 DB 读取种子数据，接口形式与真实平台 Adapter 保持一致。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_hospitals(self, city: str = "", keyword: str = "") -> list[dict]:
        stmt = select(Hospital).where(Hospital.is_active == True)
        if city:
            stmt = stmt.where(Hospital.city.ilike(f"%{city}%"))
        if keyword:
            stmt = stmt.where(Hospital.name.ilike(f"%{keyword}%"))
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": h.id, "name": h.name, "short_name": h.short_name,
                "city": h.city, "district": h.district, "address": h.address,
                "level": h.level, "phone": h.phone,
                "booking_url": h.booking_url,
                "platform_type": h.platform_type,
            }
            for h in rows
        ]

    async def list_departments(self, hospital_id: str, keyword: str = "") -> list[dict]:
        stmt = select(Department).where(
            Department.hospital_id == hospital_id,
            Department.is_active == True,
        )
        if keyword:
            stmt = stmt.where(Department.name.ilike(f"%{keyword}%"))
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": d.id, "name": d.name, "code": d.code,
                "category": d.category, "description": d.description, "floor": d.floor,
            }
            for d in rows
        ]

    async def list_schedules(self, department_id: str, date: str) -> list[dict]:
        stmt = select(DoctorSchedule).where(
            DoctorSchedule.department_id == department_id,
            DoctorSchedule.schedule_date == date,
            DoctorSchedule.is_available == True,
        ).order_by(DoctorSchedule.time_slot)
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": s.id, "doctor_name": s.doctor_name, "doctor_title": s.doctor_title,
                "doctor_bio": s.doctor_bio, "schedule_date": s.schedule_date,
                "time_slot": s.time_slot, "period": s.period,
                "total_quota": s.total_quota, "remaining_quota": s.remaining_quota,
                "fee": s.fee, "available": s.remaining_quota > 0,
            }
            for s in rows
        ]


# ─── V2 预留：真实 HIS 适配器框架（接口已定义，实现时填入即可）─────────────────────────

class HisAdapter:
    """
    对接医院 HIS / 互联网医院平台正式接口（V2）。

    接入步骤：
      1. 拿到医院/平台颁发的 client_id + secret（OAuth2）或 API Key
      2. 将凭证写入 .env：HIS_CLIENT_ID / HIS_CLIENT_SECRET / HIS_API_BASE
      3. 实现各方法，调用平台标准接口（参考国家卫健委 HL7/医院信息平台交互标准）
      4. 在 RegistrationService 中按 platform_type 路由到本 Adapter
    """

    def __init__(self, base_url: str, client_id: str, client_secret: str):
        self.base_url = base_url
        self.client_id = client_id
        self.client_secret = client_secret

    async def list_hospitals(self, city: str, keyword: str) -> list[dict]:
        raise NotImplementedError("HisAdapter V2 — 待接入")

    async def list_departments(self, hospital_id: str, keyword: str) -> list[dict]:
        raise NotImplementedError("HisAdapter V2 — 待接入")

    async def list_schedules(self, department_id: str, date: str) -> list[dict]:
        raise NotImplementedError("HisAdapter V2 — 待接入")

    async def lock_slot(self, slot_id: str, patient_info: dict) -> dict:
        raise NotImplementedError("HisAdapter V2 — 待接入")

    async def confirm_order(self, order_id: str) -> dict:
        raise NotImplementedError("HisAdapter V2 — 待接入")

    async def cancel_order(self, order_id: str, reason: str) -> dict:
        raise NotImplementedError("HisAdapter V2 — 待接入")


# ─── RegistrationService：业务逻辑层 ─────────────────────────────────────────────

class RegistrationService:
    """
    挂号业务服务，供 Registration API 路由和 Skill Runtime 调用。
    V1 全部走 SeedAdapter；V2 可按医院的 platform_type 路由到不同 Adapter。
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.adapter = SeedAdapter(db)  # V2: 按 platform_type 动态选择

    # ── 查询类 ──────────────────────────────────────────────────────────────────

    async def search_hospital(self, city: str = "", keyword: str = "") -> list[dict]:
        return await self.adapter.list_hospitals(city=city, keyword=keyword)

    async def search_department(self, hospital_id: str, keyword: str = "") -> list[dict]:
        return await self.adapter.list_departments(hospital_id=hospital_id, keyword=keyword)

    async def search_doctor_schedule(
        self, department_id: str, date: str
    ) -> list[dict]:
        """
        查询指定科室指定日期的排班号源。
        date 格式 YYYY-MM-DD；若传入"明天"等自然语言需在调用前转换。
        """
        return await self.adapter.list_schedules(department_id=department_id, date=date)

    async def search_by_department_name(
        self, hospital_name: str, department_name: str, date: str
    ) -> dict:
        """
        便捷方法：按医院名+科室名+日期一步查排班，供 Skill Runtime 直接调用。
        返回 {hospital, department, slots}
        """
        hospitals = await self.adapter.list_hospitals(keyword=hospital_name)
        if not hospitals:
            return {"error": f"未找到医院：{hospital_name}，请尝试更通用的关键词"}
        hospital = hospitals[0]

        departments = await self.adapter.list_departments(
            hospital_id=hospital["id"], keyword=department_name
        )
        if not departments:
            return {"error": f"在 {hospital['name']} 未找到科室：{department_name}"}
        department = departments[0]

        slots = await self.adapter.list_schedules(
            department_id=department["id"], date=date
        )
        return {
            "hospital": hospital,
            "department": department,
            "slots": slots,
            "date": date,
        }

    # ── 锁号 ─────────────────────────────────────────────────────────────────────

    async def lock_slot(
        self,
        user_id: str,
        schedule_id: str,
        patient_name: str,
        patient_id_last4: str,
        health_event_id: str | None = None,
    ) -> dict:
        """
        锁号：创建 RegistrationOrder(LOCKED)，号源剩余数 -1。
        锁号有效期 15 分钟，超时自动释放（生产环境需 Celery/APScheduler 定时任务）。
        合规要求：仅保留身份证后4位，不存明文。
        """
        # 查排班
        result = await self.db.execute(
            select(DoctorSchedule).where(DoctorSchedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if not schedule:
            return {"success": False, "error": "号源不存在"}
        if not schedule.is_available or schedule.remaining_quota <= 0:
            return {"success": False, "error": "该号源已无余号"}

        # 创建订单
        order = RegistrationOrder(
            id=str(uuid.uuid4()),
            user_id=user_id,
            schedule_id=schedule_id,
            health_event_id=health_event_id,
            patient_name=patient_name,
            patient_id_masked=f"****{patient_id_last4[-4:]}",
            status="LOCKED",
            lock_expire_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            fee=schedule.fee,
        )
        self.db.add(order)

        # 减少余号
        schedule.remaining_quota = max(0, schedule.remaining_quota - 1)
        if schedule.remaining_quota == 0:
            schedule.is_available = False

        await self.db.flush()
        await self.db.commit()

        return {
            "success": True,
            "order_id": order.id,
            "status": "LOCKED",
            "lock_expire_at": order.lock_expire_at.isoformat(),
            "fee": schedule.fee,
            "doctor_name": schedule.doctor_name,
            "doctor_title": schedule.doctor_title,
            "time_slot": schedule.time_slot,
            "schedule_date": schedule.schedule_date,
        }

    # ── 确认挂号 ──────────────────────────────────────────────────────────────────

    async def confirm_registration(self, order_id: str, user_id: str) -> dict:
        result = await self.db.execute(
            select(RegistrationOrder).where(
                RegistrationOrder.id == order_id,
                RegistrationOrder.user_id == user_id,
            )
        )
        order = result.scalar_one_or_none()
        if not order:
            return {"success": False, "error": "订单不存在"}
        if order.status != "LOCKED":
            return {"success": False, "error": f"订单状态异常：{order.status}，无法确认"}
        if order.lock_expire_at and order.lock_expire_at < datetime.now(timezone.utc):
            order.status = "CANCELLED"
            await self.db.commit()
            return {"success": False, "error": "锁号已过期，请重新选号"}

        order.status = "CONFIRMED"
        await self.db.flush()
        await self.db.commit()
        return {
            "success": True,
            "order_id": order.id,
            "status": "CONFIRMED",
            "message": "挂号成功！请携带本人证件按时就诊。",
        }

    # ── 取消挂号 ──────────────────────────────────────────────────────────────────

    async def cancel_registration(
        self, order_id: str, user_id: str, reason: str = ""
    ) -> dict:
        result = await self.db.execute(
            select(RegistrationOrder).where(
                RegistrationOrder.id == order_id,
                RegistrationOrder.user_id == user_id,
            )
        )
        order = result.scalar_one_or_none()
        if not order:
            return {"success": False, "error": "订单不存在"}
        if order.status in ("CANCELLED", "COMPLETED"):
            return {"success": False, "error": f"订单已处于 {order.status} 状态"}

        order.status = "CANCELLED"
        order.cancel_reason = reason

        # 归还号源
        sched_result = await self.db.execute(
            select(DoctorSchedule).where(DoctorSchedule.id == order.schedule_id)
        )
        schedule = sched_result.scalar_one_or_none()
        if schedule:
            schedule.remaining_quota = min(schedule.total_quota, schedule.remaining_quota + 1)
            schedule.is_available = True

        await self.db.flush()
        await self.db.commit()
        return {"success": True, "order_id": order.id, "status": "CANCELLED"}

    # ── 查询订单 ──────────────────────────────────────────────────────────────────

    async def get_registration_record(self, order_id: str, user_id: str) -> dict:
        result = await self.db.execute(
            select(RegistrationOrder).where(
                RegistrationOrder.id == order_id,
                RegistrationOrder.user_id == user_id,
            )
        )
        order = result.scalar_one_or_none()
        if not order:
            return {"success": False, "error": "订单不存在"}

        sched = await self.db.get(DoctorSchedule, order.schedule_id)
        return {
            "success": True,
            "order_id": order.id,
            "status": order.status,
            "patient_name": order.patient_name,
            "doctor_name": sched.doctor_name if sched else "",
            "doctor_title": sched.doctor_title if sched else "",
            "schedule_date": sched.schedule_date if sched else "",
            "time_slot": sched.time_slot if sched else "",
            "fee": order.fee,
            "created_at": order.created_at.isoformat(),
        }
